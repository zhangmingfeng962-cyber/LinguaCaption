from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

LANGUAGES = {
    "zh": "中文", "en": "English", "ja": "日本語", "ko": "한국어",
    "es": "Español", "fr": "Français", "de": "Deutsch", "ru": "Русский",
    "pt": "Português", "it": "Italiano", "ar": "العربية", "hi": "हिन्दी",
}


@dataclass
class Settings:
    schema_version: int = 4
    source: str = "zh"
    target: str = "zh"
    mode: str = "original"
    asr_backend: str = "auto"
    streaming_model: str = "models/asr-zh"
    streaming_threads: int = 4
    audio_device: str = "default"
    asr_model: str = "models/asr"
    translation_model: str = "models/translation"
    device: str = "cpu"
    compute_type: str = "int8"
    asr_threads: int = 4
    translation_threads: int = 2
    update_ms: int = 400
    min_audio_ms: int = 640
    endpoint_ms: int = 400
    max_utterance_ms: int = 6000
    vad_aggressiveness: int = 2
    font_family: str = ""
    font_size: int = 30
    font_weight: int = 400
    original_color: str = "#FFFFFF"
    translation_color: str = "#FFFFFF"
    outline_color: str = "#090D13"
    outline_width: float = 1.5
    shadow: bool = True
    background: str = "dark"
    background_opacity: int = 68
    max_chars: int = 34
    max_lines: int = 2
    position: str = "bottom"
    custom_x: float = 0.5
    custom_y: float = 0.83
    screen_name: str = ""
    click_through: bool = False
    safe_regions: dict[str, list[list[float]]] = field(default_factory=dict)
    subtitle_timeout_ms: int = 4000

    @property
    def use_streaming(self) -> bool:
        return self.source == "zh" and self.asr_backend in {"auto", "paraformer"}

    @property
    def needs_translation(self) -> bool:
        return self.mode != "original" and self.source != self.target

    def validate(self) -> None:
        for name in ("source", "target", "mode", "audio_device", "asr_model", "translation_model", "device",
                     "compute_type", "font_family", "background", "position", "screen_name",
                     "asr_backend", "streaming_model"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"设置 {name} 应为字符串")
        for name in ("shadow", "click_through"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"设置 {name} 应为布尔值")
        if self.source not in {"auto", *LANGUAGES} or self.target not in LANGUAGES:
            raise ValueError("识别或目标语言不受支持")
        choices = {
            "asr_backend": {"auto", "whisper", "paraformer"},
            "mode": {"original", "translation", "bilingual"},
            "device": {"cpu", "cuda"}, "compute_type": {"int8", "float32", "float16", "int8_float16"},
            "background": {"none", "dark", "glass"},
            "position": {"bottom", "top", "left", "right", "custom"},
        }
        for name, allowed in choices.items():
            if getattr(self, name) not in allowed:
                raise ValueError(f"无效设置：{name}")
        ranges = {
            "schema_version": (4, 4), "streaming_threads": (1, 16),
            "font_size": (16, 80), "font_weight": (100, 900), "outline_width": (0, 6),
            "background_opacity": (0, 95), "max_chars": (8, 80), "max_lines": (1, 4),
            "asr_threads": (1, 16), "translation_threads": (1, 8), "update_ms": (200, 2000),
            "min_audio_ms": (320, 2000), "endpoint_ms": (200, 1200),
            "max_utterance_ms": (2000, 12000), "vad_aggressiveness": (0, 3),
            "subtitle_timeout_ms": (2000, 30000),
            "custom_x": (0, 1), "custom_y": (0, 1),
        }
        for name, (low, high) in ranges.items():
            value = getattr(self, name)
            fractional = name in {"outline_width", "custom_x", "custom_y"}
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or (not fractional and not isinstance(value, int))
                    or not math.isfinite(value) or not low <= value <= high):
                raise ValueError(f"设置 {name} 应在 {low}–{high} 之间")
        for name in ("original_color", "translation_color", "outline_color"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
                raise ValueError(f"无效颜色：{name}")
            int(value[1:], 16)
        if not isinstance(self.safe_regions, dict) or not all(isinstance(key, str) for key in self.safe_regions):
            raise ValueError("安全区域应为按屏幕名称保存的字典")
        for rectangles in self.safe_regions.values():
            if not isinstance(rectangles, list) or len(rectangles) > 8:
                raise ValueError("每个屏幕最多 8 个安全区域")
            for rect in rectangles:
                if not isinstance(rect, list) or len(rect) != 4 or not all(
                        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in rect):
                    raise ValueError("无效安全区域")
                x, y, w, h = rect
                if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1
                        and x + w <= 1.000001 and y + h <= 1.000001):
                    raise ValueError("安全区域必须在屏幕内")


def load_settings(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("设置 JSON 的顶层应为对象")
    version = data.get("schema_version", 0)
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("设置版本应为整数")
    if version < 3:
        # Apply the requested readability defaults once to existing installations.
        data.update(schema_version=3, original_color="#FFFFFF", translation_color="#FFFFFF",
                    font_family="", font_weight=400, shadow=True, click_through=False,
                    subtitle_timeout_ms=max(12000, data.get("subtitle_timeout_ms", 7000)))
    if version < 4:
        data["schema_version"] = 4
        if data.get("source") == data.get("target") == "zh":
            data.update(mode="original", asr_backend="auto")
        data.setdefault("source", "en")
        data.setdefault("mode", "bilingual")
    allowed = {f.name for f in fields(Settings)}
    settings = Settings(**{k: v for k, v in data.items() if k in allowed})
    settings.validate()
    return settings


def save_settings(path: Path, settings: Settings) -> None:
    settings.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
