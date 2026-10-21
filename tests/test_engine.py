import threading
import time
from dataclasses import replace

import numpy as np

from linguacaption.config import Settings
from linguacaption.domain import Caption, RecognitionRequest
from linguacaption.engine import Engine


def test_slow_translation_is_discarded_after_new_revision(qtapp):
    entered, release = threading.Event(), threading.Event()

    class SlowTranslator:
        def translate(self, *args):
            entered.set()
            assert release.wait(1)
            return "stale"

    engine = Engine(Settings())
    received = []
    engine.event.connect(lambda *event: received.append(event))
    caption = Caption(1, 1, "old original", "en", False, time.monotonic(), 10)
    engine._latest[1] = 1
    engine._translation.put(caption)
    worker = threading.Thread(target=lambda: engine._translate_loop(SlowTranslator()), daemon=True)
    worker.start()
    assert entered.wait(1)
    with engine._latest_lock:
        engine._latest[1] = 2
    release.set()
    time.sleep(.02)
    engine.stop()
    worker.join(timeout=1)
    qtapp.processEvents()
    assert not any(kind == "translation" for _, kind, _ in received)


def test_inflight_recognition_does_not_cross_audio_gap(qtapp):
    entered, release = threading.Event(), threading.Event()

    class SlowRecognizer:
        def transcribe(self, samples):
            entered.set()
            assert release.wait(1)
            return "stale", "en"

    engine = Engine(Settings())
    received = []
    engine.event.connect(lambda *event: received.append(event))
    request = RecognitionRequest(1, 1, np.zeros(16000, np.float32), 0, 1, False)
    engine._recognition.put(request)
    worker = threading.Thread(target=lambda: engine._recognize_loop(SlowRecognizer(), False), daemon=True)
    worker.start()
    assert entered.wait(1)
    with engine._latest_lock:
        engine._audio_generation = 1
    release.set()
    time.sleep(.02)
    engine.stop()
    worker.join(timeout=1)
    qtapp.processEvents()
    assert not any(kind == "caption" for _, kind, _ in received)


def test_bounded_revision_bookkeeping(qtapp):
    class Recognizer:
        def transcribe(self, samples):
            return "hello", "en"
    engine = Engine(Settings())
    received = []
    engine.event.connect(lambda *event: received.append(event))
    worker = threading.Thread(target=lambda: engine._recognize_loop(Recognizer(), False), daemon=True)
    worker.start()
    base = RecognitionRequest(1, 1, np.zeros(16000, np.float32), 0, 1, True)
    for i in range(1, 21):
        engine._recognition.put(replace(base, utterance=i))
        deadline = time.monotonic() + 1
        while i not in engine._latest and time.monotonic() < deadline:
            time.sleep(.001)
    engine.stop()
    worker.join(timeout=1)
    assert len(engine._latest) <= 9


def test_empty_final_recognition_does_not_clear_previous_subtitle(qtapp):
    class SilentRecognizer:
        def transcribe(self, samples):
            return "", "en"

    engine = Engine(Settings())
    requests = iter([RecognitionRequest(1, 2, np.zeros(16000, np.float32), 0, 1, True), None])
    engine._recognition.get = lambda: next(requests)
    events = []
    engine.event.connect(lambda run, kind, payload: events.append(kind))
    engine._recognize_loop(SilentRecognizer(), False)
    assert "clear" not in events
