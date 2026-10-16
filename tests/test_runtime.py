import sys
from pathlib import Path

from linguacaption.config import Settings
from linguacaption.runtime import configure_model_paths, default_config_path, resource_root


def test_frozen_models_resolve_from_bundle_not_working_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    for name in ("asr", "translation"):
        folder = tmp_path / "models" / name
        folder.mkdir(parents=True)
        (folder / "model.bin").touch()
    settings = configure_model_paths(Settings())
    assert resource_root() == tmp_path
    assert Path(settings.asr_model) == tmp_path / "models/asr"
    assert Path(settings.translation_model) == tmp_path / "models/translation"


def test_custom_model_directory_is_preserved(tmp_path):
    settings = Settings(asr_model=str(tmp_path / "custom"))
    assert configure_model_paths(settings, tmp_path).asr_model == str(tmp_path / "custom")


def test_installed_config_uses_user_standard_directory(qtapp, tmp_path, monkeypatch):
    from linguacaption import runtime
    monkeypatch.setattr(runtime.QStandardPaths, "writableLocation", lambda location: str(tmp_path / "user-config"))
    assert default_config_path() == tmp_path / "user-config/settings.json"
