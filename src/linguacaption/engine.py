from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import replace

import numpy as np
from PySide6.QtCore import QObject, Signal

from .audio import create_capture
from .config import Settings
from .core.mailbox import LatestMailbox
from .core.segmenter import Segmenter
from .domain import SAMPLE_RATE, AudioChunk, Caption
from .inference import LocalTranslator, WhisperRecognizer


class Engine(QObject):
    # All payloads are delivered to Qt's GUI thread by queued signal connections.
    event = Signal(str, str, object)  # run_id, kind, payload

    def __init__(self, settings: Settings, demo: bool = False, *,
                 capture_factory=create_capture, recognizer_factory=WhisperRecognizer,
                 translator_factory=LocalTranslator) -> None:
        super().__init__()
        self.settings = replace(settings)
        self.run_id = uuid.uuid4().hex
        self.demo = demo
        self.stop_event = threading.Event()
        self._audio: queue.Queue[AudioChunk] = queue.Queue(maxsize=30)
        self._recognition = LatestMailbox(3)
        self._translation = LatestMailbox(2)
        self._latest: dict[int, int] = {}
        self._latest_lock = threading.Lock()
        self._audio_dropped = 0
        self._threads: list[threading.Thread] = []
        self._capture = None
        self._supervisor: threading.Thread | None = None
        self._last_level = 0.0
        self._last_drop = 0
        self._audio_generation = 0
        self._capture_factory = capture_factory
        self._recognizer_factory = recognizer_factory
        self._translator_factory = translator_factory

    def _emit(self, kind: str, payload: object) -> None:
        if not self.stop_event.is_set() or kind == "stopped":
            self.event.emit(self.run_id, kind, payload)

    def start(self) -> None:
        self.settings.validate()
        self._supervisor = threading.Thread(target=self._run, name="session", daemon=True)
        self._supervisor.start()

    def stop(self) -> None:
        self.stop_event.set()
        self._recognition.close()
        self._translation.close()
        if self._capture:
            self._capture.stop()

    def _spawn(self, name: str, function) -> None:
        def guarded() -> None:
            try:
                function()
            except Exception as error:
                self._emit("error", str(error))
                self.stop()
        thread = threading.Thread(target=guarded, name=name, daemon=True)
        self._threads.append(thread)
        thread.start()

    def _run(self) -> None:
        try:
            if self.demo:
                self._emit("ready", "演示模式 · 示例文本，无音频采集")
                self._run_demo()
                return
            self._emit("status", "正在加载本地识别模型…")
            recognizer = self._recognizer_factory(self.settings)
            if self.stop_event.is_set():
                return
            translator = None
            if self.settings.mode != "original":
                self._emit("status", "正在加载本地翻译模型…")
                translator = self._translator_factory(self.settings)
            if self.stop_event.is_set():
                return
            import webrtcvad
            vad = webrtcvad.Vad(self.settings.vad_aggressiveness)

            def speech(frame: np.ndarray) -> bool:
                pcm = (np.clip(frame, -1, 1) * 32767).astype("<i2").tobytes()
                return vad.is_speech(pcm, SAMPLE_RATE)

            segmenter = Segmenter(self.settings, speech)
            self._capture = self._capture_factory(self.settings.audio_device)
            self._spawn("segment", lambda: self._segment_loop(segmenter))
            self._spawn("recognize", lambda: self._recognize_loop(recognizer, translator is not None))
            if translator:
                self._spawn("translate", lambda: self._translate_loop(translator))
            self._emit("ready", "模型已就绪，正在打开系统音频…")
            self._spawn("capture", lambda: self._capture.run(
                self.stop_event, self._consume, lambda message: self._emit("status", message)))
            while not self.stop_event.wait(0.1):
                pass
        except Exception as error:
            self._emit("error", str(error))
        finally:
            self.stop()
            # A new session must not overlap with previous native inference.
            # The supervisor is a daemon; closing the UI never blocks on a driver.
            for thread in self._threads:
                thread.join()
            self._emit("stopped", None)

    def _consume(self, chunk: AudioChunk) -> None:
        if self.stop_event.is_set():
            return
        try:
            self._audio.put_nowait(chunk)
        except queue.Full:
            try:
                self._audio.get_nowait()
                self._audio_dropped += 1
            except queue.Empty:
                pass
            try:
                self._audio.put_nowait(chunk)
            except queue.Full:
                self._audio_dropped += 1
        now = time.monotonic()
        if now - self._last_level >= 0.2:
            self._last_level = now
            rms = float(np.sqrt(np.mean(np.square(chunk.samples)))) if len(chunk.samples) else 0
            self._emit("level", rms)

    def _segment_loop(self, segmenter: Segmenter) -> None:
        while not self.stop_event.is_set():
            try:
                chunk = self._audio.get(timeout=0.1)
            except queue.Empty:
                continue
            before = segmenter.discontinuities
            requests = segmenter.feed(chunk)
            if segmenter.discontinuities != before:
                # Any old in-flight utterance is now stale too.
                with self._latest_lock:
                    self._latest.clear()
                    self._audio_generation = segmenter.discontinuities
                self._emit("clear", None)
            for request in requests:
                self._recognition.put(request)
            dropped = self._audio_dropped + self._recognition.dropped + self._translation.dropped
            if dropped != self._last_drop:
                self._last_drop = dropped
                self._emit("warning", f"处理跟不上播放，累计跳过 {dropped} 个音频块/待处理语句；请减小模型或增大更新间隔")

    def _recognize_loop(self, recognizer: WhisperRecognizer, translate: bool) -> None:
        while not self.stop_event.is_set():
            request = self._recognition.get()
            if request is None:
                return
            with self._latest_lock:
                if request.generation != self._audio_generation:
                    continue
            begin = time.monotonic()
            text, language = recognizer.transcribe(request.samples)
            if self.stop_event.is_set():
                return
            with self._latest_lock:
                if request.generation != self._audio_generation:
                    continue
            if not text:
                if request.final:
                    self._emit("clear", None)
                continue
            caption = Caption(request.utterance, request.revision, text, language,
                              request.final, request.speech_end_at, (time.monotonic() - begin) * 1000,
                              started_at=request.started_at)
            with self._latest_lock:
                self._latest[caption.utterance] = caption.revision
                # Bound revision bookkeeping for long viewing sessions.
                for old in list(self._latest):
                    if old < caption.utterance - 8:
                        del self._latest[old]
            self._emit("caption", caption)
            if translate:
                self._translation.put(caption)

    def _translate_loop(self, translator: LocalTranslator) -> None:
        while not self.stop_event.is_set():
            caption = self._translation.get()
            if caption is None:
                return
            with self._latest_lock:
                if self._latest.get(caption.utterance) != caption.revision:
                    continue
            begin = time.monotonic()
            try:
                text = translator.translate(caption.original, caption.language, self.settings.target)
            except Exception as error:
                self._emit("warning", f"翻译失败：{error}")
                continue
            with self._latest_lock:
                fresh = self._latest.get(caption.utterance) == caption.revision
            if fresh:
                self._emit("translation", replace(caption, translation=text,
                                                   translation_ms=(time.monotonic() - begin) * 1000))

    def _run_demo(self) -> None:
        # Deliberately no fabricated latency/CPU or ASR claims in demo mode.
        examples = [
            ("The best way to understand the world is to keep exploring.", "理解世界最好的方式，是不断探索。"),
            ("A small change in perspective can open up new possibilities.", "换一个小小的视角，就能发现新的可能。"),
            ("Take your time. Every conversation is a new beginning.", "慢慢来，每一段对话都是新的开始。"),
        ]
        utterance = 0
        while not self.stop_event.is_set():
            for original, translation in examples:
                utterance += 1
                for revision, words in enumerate((original[:30], original), 1):
                    caption = Caption(utterance, revision, words, "en", revision == 2,
                                      time.monotonic(), 0, translation if revision == 2 else "")
                    self._emit("caption", caption)
                    if revision == 2:
                        self._emit("translation", caption)
                    if self.stop_event.wait(0.7 if revision == 1 else 4):
                        return
