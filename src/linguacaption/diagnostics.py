"""Explicit release self-test; never records audio or contacts a server."""
from __future__ import annotations

import json
import platform
import traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase

from . import __version__
from .config import Settings
from .inference import LocalTranslator, WhisperRecognizer
from .runtime import is_bundled, models_ready
from .ui import MainWindow


def run_packaged_test(app, settings: Settings, config_path: Path, report_path: Path,
                      audio: Path | None = None) -> int:
    result = {"version": __version__, "platform": platform.platform(), "bundled": is_bundled(),
              "models_present": models_ready(settings), "audio_capture": False, "ok": False}
    if app.platformName() in {"offscreen", "minimal"}:
        # The offscreen Windows plugin does not enumerate installed system fonts.
        for font in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf",
                     "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
                     "/System/Library/Fonts/Supplemental/Arial.ttf"):
            if Path(font).is_file():
                QFontDatabase.addApplicationFont(font)
    window = MainWindow(settings, config_path, register_hotkeys=False)
    window.show()
    exit_code = 1

    def test() -> None:
        nonlocal exit_code
        try:
            import av
            import ctranslate2
            import sentencepiece
            import webrtcvad

            from .audio import AudioResampler
            result["modules"] = {"av": av.__version__, "ctranslate2": ctranslate2.__version__,
                                 "sentencepiece": sentencepiece.__version__,
                                 "vad_silence": webrtcvad.Vad(2).is_speech(bytes(640), 16000)}
            if platform.system() == "Windows":
                import soundcard
                result["soundcard_imported"] = soundcard is not None
            samples = AudioResampler().convert(np.zeros(4800, dtype=np.float32))
            if not len(samples):
                raise RuntimeError("Audio resampling failed")
            recognizer = WhisperRecognizer(settings)
            translator = LocalTranslator(settings)
            result["asr_loaded"] = True
            result["translation"] = translator.translate("Hello world!", "en", "zh")
            if not result["translation"]:
                raise RuntimeError("Translation was empty")
            if audio:
                from faster_whisper.audio import decode_audio
                text, language = recognizer.transcribe(decode_audio(str(audio)))
                result["transcript"], result["language"] = text, language
                if not text:
                    raise RuntimeError("ASR returned no text for the supplied fixture")
            window.overlay.set_text("Hello world!", str(result["translation"]))
            app.processEvents()
            if not window.overlay.rows or any(row.path.isEmpty() for row in window.overlay.rows):
                raise RuntimeError("Subtitle glyph paths are empty")
            result["subtitle_rows"] = len(window.overlay.rows)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(report_path.with_suffix(".png")))
            result["ok"] = True
            exit_code = 0
        except Exception:
            result["error"] = traceback.format_exc()
        finally:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            window.close()
            app.quit()

    QTimer.singleShot(200, test)
    app.exec()
    return exit_code
