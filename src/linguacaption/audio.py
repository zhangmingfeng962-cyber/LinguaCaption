"""System audio only. No microphone fallback and no audio files on disk."""
from __future__ import annotations

import os
import platform
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

import av
import numpy as np

from .domain import SAMPLE_RATE, AudioChunk


class AudioResampler:
    def __init__(self, rate: int = 48000) -> None:
        self.rate = rate
        self._resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)

    def convert(self, mono: np.ndarray) -> np.ndarray:
        frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(mono.reshape(1, -1), dtype=np.float32),
                                         format="flt", layout="mono")
        frame.sample_rate = self.rate
        result = self._resampler.resample(frame)
        return np.concatenate([f.to_ndarray().ravel() for f in result]) if result else np.empty(0, np.float32)


class ChunkClock:
    def __init__(self) -> None:
        self.position = 0
        self.origin: float | None = None

    def chunk(self, samples: np.ndarray) -> AudioChunk:
        # Estimated capture clock; hardware/output buffering is not observable here.
        if self.origin is None:
            self.origin = time.monotonic() - len(samples) / SAMPLE_RATE
        started_at = self.origin + self.position / SAMPLE_RATE
        result = AudioChunk(samples.copy(), self.position, started_at)
        self.position += len(samples)
        return result


@contextmanager
def windows_com():
    import ctypes
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = ctypes.c_long
    result = ole32.CoInitializeEx(None, 0)
    # COM is per-thread. SoundCard initializes only its importing thread.
    # RPC_E_CHANGED_MODE means this thread already has a compatible apartment.
    if result not in (0, 1) and result & 0xFFFFFFFF != 0x80010106:
        raise OSError(f"COM initialization failed: {result & 0xFFFFFFFF:#x}")
    try:
        yield
    finally:
        if result in (0, 1):
            ole32.CoUninitialize()


def windows_outputs() -> list[tuple[str, str]]:
    import soundcard as sc
    with windows_com():
        return [(speaker.id, speaker.name) for speaker in sc.all_speakers()]


class WindowsLoopback:
    def __init__(self, device: str = "default") -> None:
        self.device = device

    def stop(self) -> None:
        pass  # The 50 ms read loop observes the shared stop event.

    def run(self, stop: threading.Event, consume: Callable[[AudioChunk], None],
            status: Callable[[str], None]) -> None:
        import soundcard as sc
        with windows_com():
            self._record(sc, stop, consume, status)

    def _record(self, sc, stop, consume, status) -> None:
        speaker = sc.default_speaker() if self.device == "default" else sc.get_speaker(self.device)
        if speaker is None:
            raise RuntimeError("没有可用的系统输出设备；请先连接扬声器或耳机")
        # The output ID, not a fuzzy microphone name, selects the loopback endpoint.
        loopback = sc.get_microphone(id=speaker.id, include_loopback=True)
        if not loopback.isloopback:
            raise RuntimeError("选中的端点不支持 WASAPI loopback")
        resampler, clock = AudioResampler(), ChunkClock()
        # Retain all hardware channels and downmix ourselves. SoundCard documents
        # a Windows single-channel capture issue; requesting mono is avoided.
        with loopback.recorder(samplerate=48000, channels=list(range(speaker.channels)),
                               blocksize=4800) as recorder:
            status(f"正在内录：{speaker.name}")
            while not stop.is_set():
                raw = recorder.record(numframes=2400)
                if not len(raw):
                    continue
                samples = resampler.convert(raw.mean(axis=1, dtype=np.float32))
                if len(samples):
                    consume(clock.chunk(samples))


def macos_helper() -> Path:
    override = os.environ.get("LINGUACAPTION_AUDIO_HELPER")
    if override:
        return Path(override).resolve()
    return Path(__file__).parent / "native/macos/AudioCapture.app/Contents/MacOS/AudioCapture"


class MacSystemAudio:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def stop(self) -> None:
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()  # Unblocks stdout.read on the capture thread.

    def run(self, stop: threading.Event, consume: Callable[[AudioChunk], None],
            status: Callable[[str], None]) -> None:
        if int(platform.mac_ver()[0].split(".")[0] or 0) < 13:
            raise RuntimeError("原生系统音频采集需要 macOS 13 或更新版本")
        helper = macos_helper()
        if not helper.is_file():
            raise RuntimeError("未找到 macOS 采集程序；请在项目根目录运行 bash scripts/build_macos.sh")
        errors: deque[str] = deque(maxlen=20)
        with self._lock:
            if stop.is_set():
                return
            self._process = subprocess.Popen([str(helper)], stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, bufsize=0)
            process = self._process

        def read_errors() -> None:
            assert process.stderr
            for line in process.stderr:
                message = line.decode("utf-8", errors="replace").strip()
                if message == "READY":
                    status("正在内录：macOS 系统音频")
                elif message:
                    errors.append(message)

        stderr_thread = threading.Thread(target=read_errors, daemon=True)
        stderr_thread.start()
        assert process.stdout
        resampler, clock = AudioResampler(), ChunkClock()
        pending = b""
        status("正在申请系统音频权限；首次授权后可能需要重启应用")
        try:
            while not stop.is_set():
                data = process.stdout.read(2400 * 4)
                if not data:
                    if not stop.is_set():
                        stderr_thread.join(timeout=0.5)
                        raise RuntimeError("系统音频采集已退出：" + (" / ".join(errors) or "请检查屏幕与系统音频录制权限"))
                    break
                pending += data
                complete = len(pending) // 4 * 4
                if not complete:
                    continue
                mono = np.frombuffer(pending[:complete], dtype="<f4").copy()
                pending = pending[complete:]
                samples = resampler.convert(mono)
                if len(samples):
                    consume(clock.chunk(samples))
        finally:
            self.stop()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            process.stdout.close()
            if process.stderr:
                process.stderr.close()


def create_capture(device: str = "default") -> WindowsLoopback | MacSystemAudio:
    if platform.system() == "Windows":
        return WindowsLoopback(device)
    if platform.system() == "Darwin":
        return MacSystemAudio()
    raise RuntimeError("实时内录目前支持 Windows 与 macOS；可使用 --demo 预览界面")
