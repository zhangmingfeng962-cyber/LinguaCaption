"""Explicit release self-test; never records audio or contacts a server."""
from __future__ import annotations

import json
import os
import platform
import traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QFontDatabase, QMouseEvent

from . import __version__
from .config import Settings
from .core.chinese import simplified
from .core.presentation import CaptionPresenter
from .domain import Caption
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
            elif platform.system() == "Darwin":
                from .audio import macos_helper
                helper = macos_helper()
                if not helper.is_file() or not os.access(helper, os.X_OK):
                    raise RuntimeError("Bundled system-audio helper is missing or not executable")
                result["system_audio_helper_present"] = True
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
            chinese = simplified("這是繁體字幕，臺灣與世界。", "zh")
            if chinese != "这是繁体字幕，台湾与世界。":
                raise RuntimeError("Bundled Chinese conversion data is missing or incorrect")
            reader = CaptionPresenter(Settings())
            first = Caption(1, 1, "First sentence", "en", True, 0, 0, "第一句字幕")
            following = Caption(2, 1, "Second sentence", "en", True, 0, 0, "第二句字幕")
            if reader.push(first, 0) != first or reader.push(following, 1) is not None:
                raise RuntimeError("Reading buffer replaced a caption too soon")
            if reader.advance(3.99) is not None or reader.advance(4) != following:
                raise RuntimeError("Minimum subtitle reading time is incorrect")
            overlay = window.overlay
            overlay.set_text("Hello world!", chinese)
            app.processEvents()
            if not overlay.rows or any(row.path.isEmpty() for row in overlay.rows):
                raise RuntimeError("Subtitle glyph paths are empty")
            start = overlay.mapToGlobal(QPoint(40, 60))
            end = start + QPoint(30, -80)
            for kind, point, button, buttons in (
                    (QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
                    (QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)):
                app.sendEvent(overlay, QMouseEvent(kind, QPointF(overlay.mapFromGlobal(point)), QPointF(point),
                                                  button, buttons, Qt.KeyboardModifier.NoModifier))
            geometry = overlay.geometry()
            overlay.set_text("Dragging while captions update", "更新字幕时仍然可以拖动。")
            if overlay.geometry() != geometry:
                raise RuntimeError("Live text interrupted an active drag")
            app.sendEvent(overlay, QMouseEvent(QEvent.Type.MouseButtonRelease,
                          QPointF(overlay.mapFromGlobal(end)), QPointF(end), Qt.MouseButton.LeftButton,
                          Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
            if settings.position != "custom" or overlay._drag_offset is not None:
                raise RuntimeError("Subtitle drag position was not committed")
            result["subtitle_rows"] = len(overlay.rows)
            result["readability"] = {"simplified_chinese": chinese, "minimum_hold_ms": 4000,
                                      "live_drag": True, "colors": [row.color.name() for row in overlay.rows],
                                      "system_font": QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family(),
                                      "shadow": settings.shadow}
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
