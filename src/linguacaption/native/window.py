"""Optional compositor effects. Failure always falls back to translucent black."""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication


class NativeWindow:
    def __init__(self, widget) -> None:
        self.widget = widget
        self.available = QGuiApplication.platformName() not in {"offscreen", "minimal"}
        self._mac_root = None
        self._mac_view = None
        self._effects: list = []
        self.glass_active = False
        self.failure = ""

    def configure(self) -> None:
        if not self.available or sys.platform != "darwin":
            return
        try:
            import objc
            from AppKit import NSFloatingWindowLevel
            view = objc.objc_object(c_void_p=int(self.widget.winId()))
            window = view.window()
            # All Spaces + full-screen auxiliary; exclusive/DRM video may still
            # prohibit composition by other apps.
            window.setCollectionBehavior_(window.collectionBehavior() | (1 << 0) | (1 << 8))
            window.setLevel_(NSFloatingWindowLevel)
            window.setHidesOnDeactivate_(False)
        except Exception as error:
            self.failure = str(error)

    def glass(self, enabled: bool, rects: list[QRect], opacity: int) -> bool:
        if not self.available:
            self.glass_active = False
            return False
        try:
            if sys.platform == "win32":
                self.glass_active = self._windows_glass(enabled, rects, opacity)
            elif sys.platform == "darwin":
                self.glass_active = self._mac_glass(enabled, rects)
            else:
                self.glass_active = False
        except Exception as error:
            self.failure = str(error)
            self.glass_active = False
        return self.glass_active

    def _windows_glass(self, enabled: bool, rects: list[QRect], opacity: int) -> bool:
        # Accent is a best-effort Win10/11 compositor API, feature-detected. It
        # has no stable public contract. See README's platform limitations.
        from ctypes import wintypes

        class Accent(ctypes.Structure):
            _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int),
                        ("color", ctypes.c_uint32), ("animation", ctypes.c_int)]

        class CompositionData(ctypes.Structure):
            _fields_ = [("attribute", ctypes.c_int), ("data", ctypes.c_void_p), ("size", ctypes.c_size_t)]

        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        function = getattr(user32, "SetWindowCompositionAttribute", None)
        if not function:
            return False
        function.argtypes = [wintypes.HWND, ctypes.POINTER(CompositionData)]
        function.restype = wintypes.BOOL
        user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
        gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
        gdi32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
        gdi32.CreateRectRgn.restype = wintypes.HRGN
        gdi32.CombineRgn.argtypes = [wintypes.HRGN, wintypes.HRGN, wintypes.HRGN, ctypes.c_int]
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        hwnd = int(self.widget.winId())
        alpha = int(opacity * 255 / 100)
        accent = Accent(4 if enabled else 0, 2, (alpha << 24) | 0x00150E0A, 0)
        data = CompositionData(19, ctypes.addressof(accent), ctypes.sizeof(accent))
        success = bool(function(hwnd, ctypes.byref(data)))
        if enabled and success:
            # Restrict the native blur to each line, keeping backgrounds adaptive.
            scale = self.widget.devicePixelRatioF()
            combined = gdi32.CreateRectRgn(0, 0, 0, 0)
            for rect in rects:
                part = gdi32.CreateRoundRectRgn(
                    round(rect.x() * scale), round(rect.y() * scale),
                    round((rect.x() + rect.width()) * scale), round((rect.y() + rect.height()) * scale),
                    round(14 * scale), round(14 * scale))
                gdi32.CombineRgn(combined, combined, part, 2)  # RGN_OR
                gdi32.DeleteObject(part)
            if not user32.SetWindowRgn(hwnd, combined, True):
                gdi32.DeleteObject(combined)
                return False
            # Windows owns combined after SetWindowRgn succeeds.
        else:
            user32.SetWindowRgn(hwnd, None, True)
        return enabled and success

    def _mac_glass(self, enabled: bool, rects: list[QRect]) -> bool:
        import objc
        from AppKit import (
            NSView,
            NSViewHeightSizable,
            NSViewWidthSizable,
            NSVisualEffectBlendingModeBehindWindow,
            NSVisualEffectMaterialHUDWindow,
            NSVisualEffectStateActive,
            NSVisualEffectView,
        )
        from Foundation import NSMakeRect
        if not self._mac_root and enabled:
            view = objc.objc_object(c_void_p=int(self.widget.winId()))
            window = view.window()
            root = NSView.alloc().initWithFrame_(view.frame())
            root.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            # Put native materials behind the transparent Qt content view.
            view.retain()
            view.removeFromSuperview()
            window.setContentView_(root)
            view.setFrame_(root.bounds())
            view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            root.addSubview_(view)
            view.release()
            self._mac_root, self._mac_view = root, view
        for effect in self._effects:
            effect.removeFromSuperview()
        self._effects.clear()
        if not enabled:
            return False
        height = self._mac_root.bounds().size.height
        for rect in rects:
            effect = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(
                rect.x(), height - rect.y() - rect.height(), rect.width(), rect.height()))
            effect.setMaterial_(NSVisualEffectMaterialHUDWindow)
            effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
            effect.setState_(NSVisualEffectStateActive)
            effect.setWantsLayer_(True)
            effect.layer().setCornerRadius_(7)
            effect.layer().setMasksToBounds_(True)
            self._mac_root.addSubview_positioned_relativeTo_(effect, -1, self._mac_view)
            self._effects.append(effect)
        return True
