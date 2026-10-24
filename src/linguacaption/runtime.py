from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .config import Settings


def is_bundled() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_bundled():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def default_config_path() -> Path:
    # Installations and .app bundles may be read-only. Never write next to the executable.
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    if not location:
        raise OSError("无法找到可写的用户设置目录，请用 --config 指定路径")
    return Path(location) / "settings.json"


def configure_model_paths(settings: Settings, root: Path | None = None) -> Settings:
    root = root or resource_root()
    for field, relative, marker in (("asr_model", "models/asr", "model.bin"),
                                     ("streaming_model", "models/asr-zh", "encoder.int8.onnx"),
                                     ("translation_model", "models/translation", "model.bin")):
        if getattr(settings, field) == relative:
            candidate = root / relative
            if (candidate / marker).is_file():
                setattr(settings, field, str(candidate.resolve()))
    return settings


def models_ready(settings: Settings) -> bool:
    from .streaming import STREAMING_FILES
    required = [(settings.streaming_model, STREAMING_FILES)] if settings.use_streaming else [
        (settings.asr_model, ("model.bin", "tokenizer.json", "preprocessor_config.json"))]
    if settings.needs_translation:
        required.append((settings.translation_model, ("model.bin", "sentencepiece.bpe.model", "linguacaption.json")))
    return all((Path(directory) / filename).is_file() for directory, names in required for filename in names)
