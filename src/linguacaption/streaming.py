"""Offline, stateful Mandarin ASR. One instance belongs to one worker thread."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np

from .config import Settings
from .domain import SAMPLE_RATE, AudioChunk, Caption
from .inference import require_files

STREAMING_FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt", "linguacaption.json")


def verify_streaming_model(directory: str) -> Path:
    path = require_files(directory, STREAMING_FILES, "中文流式识别")
    manifest = json.loads((path / "linguacaption.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "paraformer-online-int8-v1":
        raise RuntimeError("中文流式模型格式不匹配，请准备 asr-zh 模型")
    for name in STREAMING_FILES[:-1]:
        with (path / name).open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if manifest.get("sha256", {}).get(name) != actual:
            raise RuntimeError(f"中文模型校验失败：{name}")
    return path


class MandarinRecognizer:
    def __init__(self, settings: Settings) -> None:
        import sherpa_onnx
        import webrtcvad

        path = verify_streaming_model(settings.streaming_model)
        self.model = sherpa_onnx.OnlineRecognizer.from_paraformer(
            tokens=str(path / "tokens.txt"), encoder=str(path / "encoder.int8.onnx"),
            decoder=str(path / "decoder.int8.onnx"), num_threads=settings.streaming_threads,
            sample_rate=SAMPLE_RATE, provider="cpu", enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4, rule2_min_trailing_silence=max(.6, settings.endpoint_ms / 1000),
            rule3_min_utterance_length=max(20, settings.max_utterance_ms / 1000),
        )
        self.vad = webrtcvad.Vad(settings.vad_aggressiveness)
        self.utterance = 0
        self.discontinuities = 0
        self._expected: int | None = None
        self._new_stream()

    def _new_stream(self, keep_audio: bool = False) -> None:
        if keep_audio:
            # Endpoint reset preserves buffered look-ahead audio in the native
            # stream. Creating a fresh stream here would discard unheard samples.
            self.model.reset(self.stream)
        else:
            self.stream = self.model.create_stream()
        self.utterance += 1
        self._text = ""
        self._revision = 0
        self._started_at = self._speech_end = 0.0
        self._voiced = False
        self._vad_pending = np.empty(0, np.int16)
        self._vad_at = 0.0

    def reset(self) -> None:
        self._expected = None
        self._new_stream()

    def _caption(self, final: bool, elapsed: float) -> Caption | None:
        text = self.model.get_result(self.stream).strip()
        if not text or not self._voiced or (text == self._text and not final):
            return None
        self._text = text
        self._revision += 1
        return Caption(self.utterance, self._revision, text, "zh", final,
                       self._speech_end, elapsed, started_at=self._started_at)

    def push_audio(self, chunk: AudioChunk) -> list[Caption]:
        if self._expected is not None and chunk.start_sample != self._expected:
            self.discontinuities += 1
            self.reset()
        self._expected = chunk.start_sample + len(chunk.samples)
        pcm = (np.clip(chunk.samples, -1, 1) * 32767).astype("<i2")
        if not len(self._vad_pending):
            self._vad_at = chunk.started_at
        self._vad_pending = np.concatenate((self._vad_pending, pcm))
        while len(self._vad_pending) >= 320:
            frame = self._vad_pending[:320]
            self._vad_pending = self._vad_pending[320:]
            if self.vad.is_speech(frame.tobytes(), SAMPLE_RATE):
                if not self._voiced:
                    self._started_at = self._vad_at
                self._voiced = True
                self._speech_end = self._vad_at + .02
            self._vad_at += .02
        begin = time.monotonic()
        self.stream.accept_waveform(SAMPLE_RATE, chunk.samples)
        while self.model.is_ready(self.stream):
            self.model.decode_stream(self.stream)
        final = self.model.is_endpoint(self.stream)
        caption = self._caption(final, (time.monotonic() - begin) * 1000)
        if final:
            self._new_stream(keep_audio=True)
        return [caption] if caption else []

    def finish(self) -> list[Caption]:
        """Flush a finite replay fixture; stopping capture discards outstanding work."""
        begin = time.monotonic()
        self.stream.accept_waveform(SAMPLE_RATE, np.zeros(SAMPLE_RATE, np.float32))
        self.stream.input_finished()
        while self.model.is_ready(self.stream):
            self.model.decode_stream(self.stream)
        caption = self._caption(True, (time.monotonic() - begin) * 1000)
        self._new_stream()
        return [caption] if caption else []
