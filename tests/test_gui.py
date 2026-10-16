import time

from linguacaption.config import Settings
from linguacaption.domain import Caption
from linguacaption.ui import MainWindow


def test_overlay_preview_hide_lock_and_impossible_safety(qtapp, tmp_path):
    window = MainWindow(Settings(), tmp_path / "config.json", register_hotkeys=False)
    window.show()
    qtapp.processEvents()
    window.preview_overlay()
    qtapp.processEvents()
    assert window.overlay.isVisible()
    assert window.overlay.rows
    widths = {round(row.rect.width()) for row in window.overlay.rows}
    assert len(widths) > 1  # Each line background shrinks independently.
    window.toggle_lock()
    assert window.settings.click_through
    window.toggle_lock()
    window.toggle_visibility()
    assert not window.overlay.isVisible()
    window.toggle_visibility()
    from linguacaption.overlay import screen_key, selected_screen
    key = screen_key(selected_screen(window.settings))
    window.settings.safe_regions[key] = [[0, 0, 1, 1]]
    window.overlay.refresh()
    assert not window.overlay.isVisible()
    assert "没有足够" in window.status_message.text()
    window.close()


def test_late_translation_never_replaces_new_caption(qtapp, tmp_path):
    window = MainWindow(Settings(), tmp_path / "config.json", register_hotkeys=False)
    first = Caption(1, 1, "old", "en", False, time.monotonic(), 20)
    newer = Caption(1, 2, "new", "en", True, time.monotonic(), 20)
    window._accept_caption(first, False)
    window._accept_caption(newer, False)
    stale = Caption(1, 1, "old", "en", False, time.monotonic(), 20, "旧译文", 10)
    window._accept_caption(stale, True)
    assert window.overlay.original == "new"
    assert window.overlay.translation == ""
    window.close()


def test_missing_model_reports_error_and_stops_cleanly(qtapp, tmp_path):
    window = MainWindow(Settings(asr_model=str(tmp_path / "missing")), tmp_path / "config.json",
                        register_hotkeys=False)
    window.start_session()
    deadline = time.monotonic() + 3
    while window._engine and time.monotonic() < deadline:
        qtapp.processEvents()
        time.sleep(.01)
    assert window._engine is None
    assert "模型不完整" in window.status_message.text()
    assert window.start_button.isEnabled()
    window.close()


def test_demo_can_start_and_stop_without_audio_or_models(qtapp, tmp_path):
    window = MainWindow(Settings(), tmp_path / "config.json", demo=True, register_hotkeys=False)
    window.start_session()
    deadline = time.monotonic() + 2
    while not window._last_caption and time.monotonic() < deadline:
        qtapp.processEvents()
        time.sleep(.01)
    assert window._last_caption
    assert window.metric_values["asr"].text() == "演示"
    engine = window._engine
    window.toggle_session()
    while window._engine and time.monotonic() < deadline:
        qtapp.processEvents()
        time.sleep(.01)
    assert window._engine is None and engine.stop_event.is_set()
    assert not window.overlay.isVisible()
    window.close()


def test_closing_safety_picker_restores_main_window(qtapp, tmp_path):
    window = MainWindow(Settings(), tmp_path / "config.json", register_hotkeys=False)
    window.show()
    window.pick_safety()
    qtapp.processEvents()
    assert window._picker is not None
    assert not window.isVisible()
    window._picker.close()
    qtapp.processEvents()
    assert window._picker is None
    assert window.isVisible()
    window.close()
