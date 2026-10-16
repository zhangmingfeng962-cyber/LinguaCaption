from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class AudioChunk:
    samples: np.ndarray
    start_sample: int
    # Estimate of when the first sample reached the capture backend; monotonic seconds.
    started_at: float


@dataclass(frozen=True)
class RecognitionRequest:
    utterance: int
    revision: int
    samples: np.ndarray
    started_at: float
    speech_end_at: float
    final: bool
    generation: int = 0


@dataclass(frozen=True)
class Caption:
    utterance: int
    revision: int
    original: str
    language: str
    final: bool
    speech_end_at: float
    asr_ms: float
    translation: str = ""
    translation_ms: float | None = None
    started_at: float = 0.0

    @property
    def key(self) -> tuple[int, int]:
        return self.utterance, self.revision
