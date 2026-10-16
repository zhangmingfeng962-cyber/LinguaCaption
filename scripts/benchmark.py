"""Replay a local audio fixture through the actual runtime at playback speed.

Does not open a microphone/loopback device. Measures software timestamps,
not external speaker-to-photon latency. Reference text is supplied by the user.
"""
from __future__ import annotations

import argparse
import json
import platform
import threading
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
import psutil
import regex
from faster_whisper.audio import decode_audio
from PySide6.QtCore import QCoreApplication, QTimer

from linguacaption.config import Settings
from linguacaption.domain import SAMPLE_RATE, AudioChunk
from linguacaption.engine import Engine


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    row = list(range(len(hypothesis) + 1))
    for i, source in enumerate(reference, 1):
        new = [i]
        for j, target in enumerate(hypothesis, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j - 1] + (source != target)))
        row = new
    return row[-1]


def error_rate(reference: str, hypothesis: str, metric: str) -> float | None:
    def normalize(text: str) -> list[str]:
        text = regex.sub(r"[^\p{L}\p{N}\s]", "", text.lower())
        return regex.findall(r"\X", "".join(text.split())) if metric == "cer" else text.split()
    expected, actual = normalize(reference), normalize(hypothesis)
    return edit_distance(expected, actual) / len(expected) if expected else None


class FixtureCapture:
    def __init__(self, samples: np.ndarray) -> None:
        self.samples = np.concatenate((samples, np.zeros(SAMPLE_RATE, np.float32)))
        self.finished_at: float | None = None

    def stop(self) -> None:
        pass

    def run(self, stop: threading.Event, consume, status) -> None:
        origin = time.monotonic()
        status("Replaying local fixture; no system capture")
        for pos in range(0, len(self.samples), 800):
            block = self.samples[pos:pos + 800]
            due = origin + (pos + len(block)) / SAMPLE_RATE
            if stop.wait(max(0, due - time.monotonic())):
                return
            consume(AudioChunk(block, pos, origin + pos / SAMPLE_RATE))
        self.finished_at = time.monotonic()
        stop.wait()


def percentile(values: list[float]) -> dict:
    return {"p50_ms": round(float(np.percentile(values, 50)), 1),
            "p95_ms": round(float(np.percentile(values, 95)), 1), "n": len(values)} if values else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--asr-model", required=True)
    parser.add_argument("--translation-model", help="Optional; omitted means original-only")
    parser.add_argument("--language", default="en")
    parser.add_argument("--target", default="zh")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--metric", choices=("wer", "cer"), default="wer")
    parser.add_argument("--drain-seconds", type=float, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    samples = decode_audio(str(args.audio), sampling_rate=SAMPLE_RATE)
    fixture = FixtureCapture(samples)
    settings = Settings(asr_model=args.asr_model, source=args.language, target=args.target,
                        translation_model=args.translation_model or "models/translation",
                        mode="bilingual" if args.translation_model else "original")
    app = QCoreApplication([])
    engine = Engine(settings, capture_factory=lambda device: fixture)
    originals: OrderedDict[int, object] = OrderedDict()
    translations: OrderedDict[int, object] = OrderedDict()
    events = []
    errors, warnings, first = [], [], set()
    process = psutil.Process()
    cpu_started = process.cpu_times()
    begin = time.monotonic()
    last_activity = begin
    peak_rss = 0

    def receive(run_id, kind, payload):
        nonlocal last_activity
        last_activity = time.monotonic()
        if kind == "caption":
            originals[payload.utterance] = payload
        elif kind == "translation":
            translations[payload.utterance] = payload
        if kind in {"caption", "translation"}:
            event = {"kind": kind, "utterance": payload.utterance, "revision": payload.revision,
                     "final": payload.final, "asr_ms": payload.asr_ms,
                     "translation_ms": payload.translation_ms,
                     "lag_ms": (last_activity - payload.speech_end_at) * 1000}
            if kind == "caption" and payload.utterance not in first:
                event["first_caption_ms"] = (last_activity - payload.started_at) * 1000
                first.add(payload.utterance)
            events.append(event)
        elif kind == "error":
            errors.append(str(payload))
        elif kind == "warning":
            warnings.append(str(payload))
        elif kind == "stopped":
            app.quit()

    engine.event.connect(receive)

    def tick():
        nonlocal peak_rss
        peak_rss = max(peak_rss, process.memory_info().rss)
        if fixture.finished_at is not None:
            if time.monotonic() - max(fixture.finished_at, last_activity) >= args.drain_seconds:
                engine.stop()
        if time.monotonic() - begin > len(samples) / SAMPLE_RATE + 180:
            errors.append("Benchmark timeout")
            engine.stop()
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(100)
    engine.start()
    app.exec()
    duration = time.monotonic() - begin
    cpu_ended = process.cpu_times()
    cpu_seconds = cpu_ended.user + cpu_ended.system - cpu_started.user - cpu_started.system
    transcript = " ".join(c.original for c in originals.values())
    result = {
        "platform": platform.platform(), "python": platform.python_version(),
        "audio_seconds": len(samples) / SAMPLE_RATE, "settings": {
            "source": settings.source, "target": settings.target, "update_ms": settings.update_ms,
            "min_audio_ms": settings.min_audio_ms, "endpoint_ms": settings.endpoint_ms,
            "asr_threads": settings.asr_threads, "translation_threads": settings.translation_threads,
            "mode": settings.mode, "asr_model": str(Path(args.asr_model).resolve()),
        },
        "transcript": transcript,
        "translated_captions": [{"original": caption.original, "translation": caption.translation}
                                for utterance, caption in translations.items()
                                if utterance in originals and originals[utterance].key == caption.key],
        "first_caption": percentile([e["first_caption_ms"] for e in events if "first_caption_ms" in e]),
        "original_lag": percentile([e["lag_ms"] for e in events if e["kind"] == "caption"]),
        "bilingual_lag": percentile([e["lag_ms"] for e in events if e["kind"] == "translation"]),
        "peak_rss_mb": round(peak_rss / 1024 ** 2, 1),
        "average_cpu_percent_total_capacity": round(cpu_seconds / duration / (psutil.cpu_count() or 1) * 100, 2),
        "cpu_window_note": "Includes model load, fixture playback, and drain time",
        "latency_note": "Software replay timestamps only; no WASAPI/ScreenCaptureKit or GUI paint timing",
        "events": events, "errors": errors, "warnings": warnings,
    }
    if args.reference:
        value = error_rate(args.reference.read_text(encoding="utf-8"), transcript, args.metric)
        result[args.metric] = value
        result["one_minus_error_rate"] = None if value is None else 1 - value
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in {"events", "settings"}},
                     ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
