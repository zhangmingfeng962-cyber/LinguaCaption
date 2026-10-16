from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

SHORTCUTS = {
    "toggle": "Ctrl + Alt + S", "swap": "Ctrl + Alt + L",
    "larger": "Ctrl + Alt + ↑", "smaller": "Ctrl + Alt + ↓", "lock": "Ctrl + Alt + K",
}


class _WindowsFilter(QAbstractNativeEventFilter):
    def __init__(self, callback, identifiers: dict[int, str]) -> None:
        super().__init__()
        self.callback, self.identifiers = callback, identifiers

    def nativeEventFilter(self, event_type, message):
        from ctypes.wintypes import MSG
        if bytes(event_type) in {b"windows_generic_MSG", b"windows_dispatcher_MSG"}:
            msg = MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.identifiers:  # WM_HOTKEY
                self.callback(self.identifiers[msg.wParam])
                return True, 0
        return False, 0


class Hotkeys(QObject):
    action = Signal(str)

    def __init__(self, application) -> None:
        super().__init__()
        self.application = application
        self._ids: dict[int, str] = {}
        self._filter = None
        self._listener = None

    def register(self) -> list[str]:
        errors = []
        if sys.platform == "win32":
            for i, (action, key) in enumerate((("toggle", 0x53), ("swap", 0x4C), ("larger", 0x26),
                                               ("smaller", 0x28), ("lock", 0x4B)), 0x5A00):
                if ctypes.windll.user32.RegisterHotKey(None, i, 0x0001 | 0x0002 | 0x4000, key):
                    self._ids[i] = action
                else:
                    # Display drivers commonly reserve Ctrl+Alt+arrow for rotation.
                    fallback = {"larger": (0xBB, "Ctrl + Alt + ="), "smaller": (0xBD, "Ctrl + Alt + -")}.get(action)
                    if fallback and ctypes.windll.user32.RegisterHotKey(None, i, 0x4003, fallback[0]):
                        self._ids[i] = action
                        errors.append(f"{SHORTCUTS[action]} 被占用，已改用 {fallback[1]}")
                    else:
                        errors.append(f"快捷键 {SHORTCUTS[action]} 已被占用")
            self._filter = _WindowsFilter(self.action.emit, self._ids)
            self.application.installNativeEventFilter(self._filter)
        elif sys.platform == "darwin":
            try:
                from pynput import keyboard
                if not keyboard.Listener.IS_TRUSTED:
                    return ["全局快捷键需要系统设置中的辅助功能/输入监控权限；界面按钮仍可使用"]
                bindings = {"<ctrl>+<alt>+s": "toggle", "<ctrl>+<alt>+l": "swap",
                            "<ctrl>+<alt>+<up>": "larger", "<ctrl>+<alt>+<down>": "smaller",
                            "<ctrl>+<alt>+k": "lock"}
                self._listener = keyboard.GlobalHotKeys({key: (lambda a=action: self.action.emit(a))
                                                         for key, action in bindings.items()})
                self._listener.start()
            except Exception as error:
                errors.append(f"无法注册快捷键：{error}")
        return errors

    def close(self) -> None:
        if sys.platform == "win32":
            for identifier in self._ids:
                ctypes.windll.user32.UnregisterHotKey(None, identifier)
            self._ids.clear()
            if self._filter:
                self.application.removeNativeEventFilter(self._filter)
        if self._listener:
            self._listener.stop()
