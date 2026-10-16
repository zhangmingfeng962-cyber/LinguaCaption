import json

import pytest
import regex

from linguacaption.config import Settings, load_settings, save_settings
from linguacaption.core.text import visible_lines, wrap_text


def test_emoji_and_cjk_wrap_without_splitting_graphemes():
    text = "你好世界👨‍👩‍👧‍👦こんにちは한국어"
    lines = wrap_text(text, 4)
    assert "".join(lines) == text
    assert all(len(regex.findall(r"\X", line)) <= 4 for line in lines)
    assert any("👨‍👩‍👧‍👦" in line for line in lines)


def test_wrap_respects_pixel_budget_and_word_boundaries():
    lines = wrap_text("Every conversation is a new beginning.", 20, 100, lambda s: len(s) * 10)
    assert all(len(line) <= 10 for line in lines)
    assert "".join(lines).replace(" ", "") == "Every conversation is a new beginning.".replace(" ", "")
    assert lines[0] == "Every"


def test_live_tail_ellipsis_never_splits_a_joined_emoji():
    assert visible_lines(["older", "👨‍👩‍👧‍👦你好"], 1) == ["…你好"]


def test_config_roundtrip_and_unknown_future_fields(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(safe_regions={"test": [[.2, .3, .1, .1]]})
    save_settings(path, settings)
    assert load_settings(path) == settings
    data = json.loads(path.read_text(encoding="utf-8"))
    data["future_field"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_settings(path) == settings


@pytest.mark.parametrize("regions", [[[0, 0, 1.2, 1]], [[.9, .9, .3, .3]], [[0, 0, float('nan'), .2]]])
def test_invalid_safety_regions_are_rejected(regions):
    with pytest.raises(ValueError):
        Settings(safe_regions={"screen": regions}).validate()


@pytest.mark.parametrize("field,value", [("font_size", 25.5), ("safe_regions", []), ("shadow", "yes")])
def test_invalid_config_types_fail_before_ui_creation(field, value):
    with pytest.raises(ValueError):
        Settings(**{field: value}).validate()
