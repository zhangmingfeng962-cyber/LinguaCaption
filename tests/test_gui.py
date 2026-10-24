import time
from dataclasses import replace

from linguacaption.config import Settings
from linguacaption.domain import Caption
from linguacaption.ui import MainWindow


def test_overlay_preview_hide_lock_and_impossible_safety(qtapp, tmp_path):
    window = MainWindow(Settings(source="en", mode="bilingual"), tmp_path / "config.json", register_hotkeys=False)
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
    window = MainWindow(Settings(source="en", mode="bilingual"), tmp_path / "config.json", register_hotkeys=False)
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
    window = MainWindow(Settings(source="en", mode="bilingual"), tmp_path / "config.json", demo=True, register_hotkeys=False)
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
    window = MainWindow(Settings(source="en", mode="bilingual"), tmp_path / "config.json", register_hotkeys=False)
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


def test_chinese_history_and_subtitles_use_simplified_text(qtapp, tmp_path):
    window = MainWindow(Settings(target="zh"), tmp_path / "config.json", register_hotkeys=False)
    source = Caption(1, 1, "這是原文", "zh", True, time.monotonic(), 20)
    window._accept_caption(source, False)
    window._accept_caption(replace(source, translation="這是臺灣的字幕"), True)
    assert window.overlay.original == "这是原文"
    assert window.overlay.translation == "这是台湾的字幕"
    assert "这是台湾的字幕" in window.history_view.toPlainText()
    assert all(row.color.name() == "#ffffff" for row in window.overlay.rows)
    window.close()


def test_drag_is_stable_while_live_text_changes(qtapp, tmp_path):
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    window = MainWindow(Settings(source="en", mode="bilingual"), tmp_path / "config.json", register_hotkeys=False)
    overlay = window.overlay
    overlay.set_text("Old caption", "原字幕")
    qtapp.processEvents()

    def mouse(kind, global_position, button, buttons, target=overlay):
        event = QMouseEvent(kind, QPointF(target.mapFromGlobal(global_position)), QPointF(global_position),
                            button, buttons, Qt.KeyboardModifier.NoModifier)
        qtapp.sendEvent(target, event)

    # The hover handle must forward drag events as well as the subtitle itself.
    overlay.toolbar.show()
    start = overlay.drag_handle.mapToGlobal(QPoint(10, 10))
    mouse(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
          overlay.drag_handle)
    assert overlay._drag_offset is not None
    stop = start + QPoint(40, -150)
    mouse(QEvent.Type.MouseMove, stop, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    moved = overlay.geometry()
    for index in range(8):
        overlay.set_text(f"Live revision {index}", "更新后的字幕")
        assert overlay.geometry() == moved
    mouse(QEvent.Type.MouseButtonRelease, stop, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    assert overlay._drag_offset is None
    assert window.settings.position == "custom"
    assert overlay.original == "Live revision 7"
    assert abs(overlay.geometry().center().y() - moved.center().y()) <= 1
    center = overlay.geometry().center()
    overlay.set_text("Another caption", "另一个字幕")
    assert abs(overlay.geometry().center().y() - center.y()) <= 1
    window.close()


def test_live_window_updates_immediately_and_stop_clears_subtitles(qtapp, tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr("linguacaption.ui.time.monotonic", lambda: now[0])
    window = MainWindow(Settings(source="en", mode="bilingual"), tmp_path / "config.json", register_hotkeys=False)
    first = Caption(1, 1, "First sentence", "en", True, 100, 20)
    window._accept_caption(first, False)
    window._accept_caption(replace(first, translation="第一句话"), True)
    now[0] = 101
    second = Caption(2, 1, "Second sentence", "en", True, 101, 20)
    window._accept_caption(second, False)
    window._accept_caption(replace(second, translation="第二句话"), True)
    assert window.overlay.translation == "第二句话"
    now[0] = 104
    window._tick()
    assert window.overlay.translation == "第二句话"
    window._accept_caption(Caption(3, 1, "Third", "en", True, 104, 20), False)
    window._clear_subtitles()
    now[0] = 200
    window._tick()
    assert window.overlay.original == "" and not window.overlay.isVisible()
    window.close()


def test_same_revision_translation_with_wrong_source_text_is_rejected(qtapp, tmp_path):
    window = MainWindow(Settings(source="en", mode="bilingual"), tmp_path / "config.json", register_hotkeys=False)
    original = Caption(1, 1, "correct", "en", False, 1, 1)
    window._accept_caption(original, False)
    window._accept_caption(replace(original, original="wrong", translation="错配"), True)
    assert window.overlay.original == "correct" and window.overlay.translation == ""
    window.mandarin_preset()
    assert window.settings.use_streaming and not window.settings.needs_translation
    window.close()
