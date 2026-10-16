import ctypes
import sys

import pytest

from linguacaption.native.hotkeys import Hotkeys


@pytest.mark.skipif(sys.platform != "win32", reason="Windows RegisterHotKey fallback")
def test_reserved_arrows_fall_back_to_usable_font_hotkeys(qtapp, monkeypatch):
    registered = []

    def register(window, identifier, modifiers, key):
        if key in (0x26, 0x28):
            return 0
        registered.append(key)
        return 1

    monkeypatch.setattr(ctypes.windll.user32, "RegisterHotKey", register)
    monkeypatch.setattr(ctypes.windll.user32, "UnregisterHotKey", lambda *args: True)
    hotkeys = Hotkeys(qtapp)
    notices = hotkeys.register()
    assert len(hotkeys._ids) == 5
    assert 0xBB in registered and 0xBD in registered
    assert len(notices) == 2 and all("已改用" in item for item in notices)
    hotkeys.close()
