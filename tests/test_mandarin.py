import json
import threading
import time

import numpy as np
import pytest

from linguacaption.config import Settings
from linguacaption.domain import AudioChunk, Caption
from linguacaption.engine import Engine
from linguacaption.streaming import MandarinRecognizer, verify_streaming_model


def test_model_corruption_fails_before_loading_native_runtime(tmp_path):
    for name in ("encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt"):
        (tmp_path / name).write_bytes(b"corrupted")
    (tmp_path / "linguacaption.json").write_text(json.dumps({
        "format": "paraformer-online-int8-v1", "sha256": {}}))
    with pytest.raises(RuntimeError, match="校验失败"):
        verify_streaming_model(str(tmp_path))


def test_chinese_original_session_never_loads_whisper_or_translator(qtapp):
    loaded = []
    processed = threading.Event()

    class Recognizer:
        def push_audio(self, chunk):
            processed.set()
            return [Caption(1, 1, "这是中文", "zh", False, 1, 1)]

        def reset(self):
            pass

    class Capture:
        def run(self, stop, consume, status):
            consume(AudioChunk(np.zeros(800, np.float32), 0, 0))
            stop.wait()

        def stop(self):
            pass

    def forbidden(settings):
        loaded.append("unexpected")
        raise AssertionError("Unnecessary model was loaded")

    engine = Engine(Settings(), streaming_factory=lambda settings: Recognizer(),
                    capture_factory=lambda device: Capture(), recognizer_factory=forbidden,
                    translator_factory=forbidden)
    engine.start()
    assert processed.wait(2)
    engine.stop()
    engine._supervisor.join(2)
    assert not engine._supervisor.is_alive() and loaded == []


def test_inflight_streaming_result_is_discarded_when_audio_queue_overflows(qtapp):
    entered, release = threading.Event(), threading.Event()

    class BlockedRecognizer:
        def push_audio(self, chunk):
            if chunk.start_sample == 0:
                entered.set()
                assert release.wait(2)
                return [Caption(1, 1, "过时字幕", "zh", False, 0, 0)]
            return []

        def reset(self):
            pass

    engine = Engine(Settings())
    events = []
    engine.event.connect(lambda run, kind, data: events.append((kind, data)))
    engine._consume(AudioChunk(np.zeros(800, np.float32), 0, 0))
    worker = threading.Thread(target=engine._streaming_loop, args=(BlockedRecognizer(), False))
    worker.start()
    assert entered.wait(1)
    for index in range(1, 20):
        engine._consume(AudioChunk(np.zeros(800, np.float32), index * 800, index * .05))
    release.set()
    time.sleep(.03)
    engine.stop()
    worker.join(2)
    qtapp.processEvents()
    assert engine._audio_dropped > 0
    assert any(kind == "clear" for kind, _ in events)
    assert not any(kind == "caption" for kind, _ in events)


def test_short_audio_chunks_are_accumulated_for_vad_without_losing_stream_audio():
    class Stream:
        def accept_waveform(self, rate, audio):
            received.append(len(audio))

    class Model:
        def create_stream(self):
            return Stream()

        def is_ready(self, stream):
            return False

        def is_endpoint(self, stream):
            return False

        def get_result(self, stream):
            return "中文"

    class VAD:
        def is_speech(self, pcm, rate):
            return True

    recognizer = MandarinRecognizer.__new__(MandarinRecognizer)
    recognizer.model, recognizer.vad = Model(), VAD()
    recognizer.utterance = recognizer.discontinuities = 0
    recognizer._expected = None
    recognizer._new_stream()
    received = []
    assert recognizer.push_audio(AudioChunk(np.ones(160, np.float32), 0, 10)) == []
    captions = recognizer.push_audio(AudioChunk(np.ones(160, np.float32), 160, 10.01))
    assert received == [160, 160] and captions[0].original == "中文"
    assert captions[0].started_at == 10 and captions[0].speech_end_at == 10.02
    # A sample gap resets context; an old result cannot be reused as a new utterance.
    assert recognizer.push_audio(AudioChunk(np.ones(160, np.float32), 800, 10.05)) == []
    assert recognizer.discontinuities == 1
