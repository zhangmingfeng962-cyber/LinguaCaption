"""Compare Mandarin ASR on referenced FLEURS clips; optionally replay through Qt in real time.

Input is a local google/fleurs cmn_hans_cn dev.tsv and extracted audio/dev/.
No microphone, system capture, or external screen timing is measured.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
from benchmark import FixtureCapture, error_rate, percentile
from faster_whisper.audio import decode_audio

from linguacaption.config import Settings
from linguacaption.core.chinese import simplified
from linguacaption.core.segmenter import Segmenter
from linguacaption.domain import SAMPLE_RATE, AudioChunk
from linguacaption.inference import WhisperRecognizer
from linguacaption.streaming import MandarinRecognizer


def fixtures(root: Path, seconds: float) -> list[dict]:
    result, duration = [], 0.0
    with (root / "dev.tsv").open(encoding="utf-8") as handle:
        for index, row in enumerate(csv.reader(handle, delimiter="\t")):
            audio = decode_audio(str(root / "audio/dev" / row[1]), sampling_rate=SAMPLE_RATE)
            scenario = "clear"
            if index % 5 == 3:
                audio = np.interp(np.arange(0, len(audio), 1.25), np.arange(len(audio)), audio).astype(np.float32)
                scenario = "fast_1.25x"
            elif index % 5 == 4:
                # Synthetic instrumental chord, explicitly labelled; not a real music corpus.
                t = np.arange(len(audio)) / SAMPLE_RATE
                chord = sum(np.sin(2 * np.pi * f * t) for f in (130.81, 164.81, 196.0)) / 3
                rms = np.sqrt(np.mean(audio ** 2))
                audio = np.clip(audio + chord * rms * .45, -1, 1).astype(np.float32)
                scenario = "synthetic_accompaniment"
            result.append({"file": row[1], "reference": row[2], "audio": audio, "scenario": scenario})
            duration += len(audio) / SAMPLE_RATE
            if duration >= seconds:
                break
    if duration < seconds:
        raise ValueError("Not enough unique referenced audio")
    return result


def batch(items: list[dict], settings: Settings, output: Path, provenance: dict | None = None) -> None:
    import webrtcvad
    stream = MandarinRecognizer(settings)
    whisper = WhisperRecognizer(settings)
    scores = []
    for index, item in enumerate(items):
        audio = item["audio"]
        stream.reset()
        parts = OrderedDict()
        begin = time.monotonic()
        for pos in range(0, len(audio), 800):
            for caption in stream.push_audio(AudioChunk(audio[pos:pos + 800], pos, pos / SAMPLE_RATE)):
                parts[caption.utterance] = caption.original
        for caption in stream.finish():
            parts[caption.utterance] = caption.original
        streamed = simplified("".join(parts.values()), "zh")
        stream_seconds = time.monotonic() - begin
        vad = webrtcvad.Vad(settings.vad_aggressiveness)
        segmenter = Segmenter(settings, lambda frame, detector=vad: detector.is_speech(
            (np.clip(frame, -1, 1) * 32767).astype("<i2").tobytes(), SAMPLE_RATE))
        parts = OrderedDict()
        begin = time.monotonic()
        padded = np.concatenate((audio, np.zeros(SAMPLE_RATE, np.float32)))
        for pos in range(0, len(padded), 800):
            for request in segmenter.feed(AudioChunk(padded[pos:pos + 800], pos, pos / SAMPLE_RATE)):
                # Same final segmentation as v0.3, without repeated partial work.
                if request.final:
                    text, _ = whisper.transcribe(request.samples)
                    parts[request.utterance] = text
        baseline = simplified("".join(parts.values()), "zh")
        record = {k: v for k, v in item.items() if k != "audio"}
        record.update(audio_seconds=len(audio) / SAMPLE_RATE, streaming=streamed, baseline=baseline,
                      streaming_cer=error_rate(item["reference"], streamed, "cer"),
                      baseline_cer=error_rate(item["reference"], baseline, "cer"),
                      streaming_compute_seconds=stream_seconds, baseline_compute_seconds=time.monotonic() - begin)
        scores.append(record)
        if (index + 1) % 10 == 0:
            output.write_text(json.dumps({"clips": scores}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Scored {index + 1}/{len(items)}", flush=True)
    summary = {}
    for scenario in ("all", "clear", "fast_1.25x", "synthetic_accompaniment"):
        selected = scores if scenario == "all" else [x for x in scores if x["scenario"] == scenario]
        summary[scenario] = {"clips": len(selected), "audio_seconds": sum(x["audio_seconds"] for x in selected)}
        # Concatenated text is safe for aggregate scoring here: clips are already aligned independently.
        # Weight per-clip CER by normalized reference length to avoid cross-boundary edit alignment.
        import regex
        lengths = [len(regex.sub(r"[^\p{L}\p{N}]", "", x["reference"].lower())) for x in selected]
        for name in ("streaming", "baseline"):
            summary[scenario][name + "_cer"] = sum(x[name + "_cer"] * n for x, n in zip(selected, lengths, strict=True)) / sum(lengths)
    output.write_text(json.dumps({"summary": summary, "clips": scores,
                                 "baseline_note": "v0.3 tiny final segmentation, ASR only; no UI retention",
                                 "provenance": provenance},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


def realtime(items: list[dict], settings: Settings, output: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import psutil
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from linguacaption.engine import Engine
    from linguacaption.ui import MainWindow

    audio = np.concatenate([np.concatenate((x["audio"], np.zeros(SAMPLE_RATE * 2, np.float32))) for x in items])
    fixture = FixtureCapture(audio)
    app = QApplication([])
    if Path("C:/Windows/Fonts/msyh.ttc").is_file():
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    window = MainWindow(settings, output.with_suffix(".settings.json"), register_hotkeys=False)
    engine = Engine(settings, capture_factory=lambda device: fixture)
    window._engine = engine
    engine.event.connect(window._engine_event)
    events, warnings, errors = [], [], []
    process = psutil.Process()
    cpu_start = process.cpu_times()
    begin = time.monotonic()
    peak = 0
    first = set()

    def receive(run, kind, payload):
        if kind == "caption":
            now = time.monotonic()
            row = {"utterance": payload.utterance, "revision": payload.revision, "final": payload.final,
                   "asr_ms": payload.asr_ms, "lag_ms": (now - payload.speech_end_at) * 1000,
                   "text": payload.original}
            if payload.utterance not in first:
                row["first_caption_ms"] = (now - payload.started_at) * 1000
                first.add(payload.utterance)
            events.append(row)
        elif kind == "warning":
            warnings.append(str(payload))
        elif kind == "error":
            errors.append(str(payload))
        elif kind == "stopped":
            app.quit()
    engine.event.connect(receive)
    last_report = 0

    def tick():
        nonlocal peak, last_report
        peak = max(peak, process.memory_info().rss)
        elapsed = time.monotonic() - begin
        if elapsed - last_report > 60:
            last_report = elapsed
            progress = {"elapsed_seconds": round(elapsed), "captions": len(events),
                        "dropped_audio_blocks": engine._audio_dropped, "rss_mb": round(process.memory_info().rss / 2**20)}
            output.with_suffix(".progress.json").write_text(json.dumps(progress), encoding="utf-8")
            print(json.dumps(progress), flush=True)
        if fixture.finished_at and time.monotonic() - fixture.finished_at > 4:
            engine.stop()
        if elapsed > len(audio) / SAMPLE_RATE + 120:
            errors.append("Replay timeout")
            engine.stop()
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(100)
    engine.start()
    app.exec()
    elapsed = time.monotonic() - begin
    cpu_end = process.cpu_times()
    result = {"audio_seconds": len(audio) / SAMPLE_RATE, "speech_fixture_seconds": sum(len(x["audio"]) / SAMPLE_RATE for x in items),
              "elapsed_seconds": elapsed, "clips": len(items), "errors": errors, "warnings": warnings,
              "dropped_audio_blocks": engine._audio_dropped, "peak_rss_mb": round(peak / 2**20, 1),
              "cpu_percent_total_capacity": (cpu_end.user + cpu_end.system - cpu_start.user - cpu_start.system) / elapsed / psutil.cpu_count() * 100,
              "original_lag_estimate": percentile([x["lag_ms"] for x in events if not x["final"]]),
              "first_caption_estimate": percentile([x["first_caption_ms"] for x in events if "first_caption_ms" in x]),
              "final_lag_estimate": percentile([x["lag_ms"] for x in events if x["final"]]),
              "measurement_note": "Realtime fixture into production Engine/UI on offscreen Qt; audio/VAD timestamps are estimates, not word alignment or external screen timing",
              "events": events}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    window._engine = None
    window.close()
    print(json.dumps({k: v for k, v in result.items() if k != "events"}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=1800)
    parser.add_argument("--mode", choices=("batch", "realtime"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    config = Settings(streaming_model=str(args.models / "asr-zh"), asr_model=str(args.models / "asr"))
    selected = fixtures(args.dataset, args.seconds)
    if args.mode == "batch":
        batch(selected, config, args.output, json.loads((args.dataset / "provenance.json").read_text()))
    else:
        realtime(selected, config, args.output)
