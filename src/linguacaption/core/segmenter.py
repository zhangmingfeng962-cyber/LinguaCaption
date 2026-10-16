from __future__ import annotations

from collections import deque
from collections.abc import Callable

import numpy as np

from ..config import Settings
from ..domain import SAMPLE_RATE, AudioChunk, RecognitionRequest

FRAME_SAMPLES = 320  # WebRTC VAD accepts 10/20/30 ms; use 20 ms.


class Segmenter:
    def __init__(self, settings: Settings, is_speech: Callable[[np.ndarray], bool]) -> None:
        self.settings = settings
        self.is_speech = is_speech
        self.utterance = 0
        self.discontinuities = 0
        self._expected: int | None = None
        self._pending = np.empty(0, dtype=np.float32)
        self._pending_at = 0.0
        self._preroll: deque[tuple[np.ndarray, float]] = deque(maxlen=10)
        self._reset_phrase()

    def _reset_phrase(self) -> None:
        self._frames: list[np.ndarray] = []
        self._start = 0.0
        self._speech_end = 0.0
        self._silence_ms = 0
        self._voiced_ms = 0
        self._last_emit_ms = 0
        self._revision = 0

    def feed(self, chunk: AudioChunk) -> list[RecognitionRequest]:
        if self._expected is not None and chunk.start_sample != self._expected:
            self.discontinuities += 1
            self._pending = np.empty(0, dtype=np.float32)
            self._preroll.clear()
            self._reset_phrase()
        self._expected = chunk.start_sample + len(chunk.samples)
        if not len(self._pending):
            self._pending_at = chunk.started_at
        self._pending = np.concatenate((self._pending, chunk.samples))
        requests = []
        while len(self._pending) >= FRAME_SAMPLES:
            frame = self._pending[:FRAME_SAMPLES].copy()
            self._pending = self._pending[FRAME_SAMPLES:]
            stamp = self._pending_at
            self._pending_at += FRAME_SAMPLES / SAMPLE_RATE
            voiced = self.is_speech(frame)
            if not self._frames:
                if not voiced:
                    self._preroll.append((frame, stamp))
                    continue
                self.utterance += 1
                self._start = self._preroll[0][1] if self._preroll else stamp
                self._frames.extend(f for f, _ in self._preroll)
                self._preroll.clear()
            self._frames.append(frame)
            self._silence_ms = 0 if voiced else self._silence_ms + 20
            if voiced:
                self._voiced_ms += 20
                self._speech_end = stamp + 0.02
            duration_ms = len(self._frames) * 20
            final = (self._silence_ms >= self.settings.endpoint_ms
                     or duration_ms >= self.settings.max_utterance_ms)
            due = (duration_ms >= self.settings.min_audio_ms
                   and duration_ms - self._last_emit_ms >= self.settings.update_ms)
            if (due or final) and self._voiced_ms >= 120:
                self._revision += 1
                self._last_emit_ms = duration_ms
                requests.append(RecognitionRequest(
                    self.utterance, self._revision, np.concatenate(self._frames),
                    self._start, self._speech_end, final, self.discontinuities,
                ))
            if final:
                # Do not reuse voiced tail after a forced boundary: no duplicate speech.
                self._reset_phrase()
        return requests
