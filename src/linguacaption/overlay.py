from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QTextLayout,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from .config import Settings
from .core.layout import Rect, place_subtitle, preferred_position
from .core.text import visible_lines, wrap_text
from .native.window import NativeWindow


def selected_screen(settings: Settings):
    return next((screen for screen in QGuiApplication.screens() if screen.name() == settings.screen_name),
                QGuiApplication.primaryScreen())


def screen_key(screen) -> str:
    return screen.name() or "default-display"


@dataclass
class TextRow:
    path: QPainterPath
    rect: QRectF
    color: QColor


def shaped_path(text: str, font: QFont) -> QPainterPath:
    # QTextLayout shapes RTL scripts and selects fallback fonts for CJK glyphs.
    layout = QTextLayout(text, font)
    layout.beginLayout()
    line = layout.createLine()
    line.setLineWidth(100_000)
    layout.endLayout()
    path = QPainterPath()
    for run in layout.glyphRuns():
        raw = run.rawFont()
        for glyph, position in zip(run.glyphIndexes(), run.positions(), strict=True):
            path.addPath(raw.pathForGlyph(glyph).translated(position))
    bounds = path.boundingRect()
    return path.translated(-bounds.x(), -bounds.y())


def build_rows(settings: Settings, original: str, translation: str, max_width: int,
               scale: float = 1, toolbar: bool = True) -> tuple[list[TextRow], QSize]:
    raw: list[tuple[QPainterPath, QColor, float]] = []
    texts = []
    if settings.mode in {"original", "bilingual"} and original:
        texts.append((original, settings.original_color, 0.83 if settings.mode == "bilingual" else 1))
    if settings.mode in {"translation", "bilingual"} and translation:
        texts.append((translation, settings.translation_color, 1))
    for text, color, size_ratio in texts:
        # QFont("") may select the bitmap MS Sans Serif font on native Windows,
        # whose Latin glyphs have no vector outlines. Inherit the app font instead.
        font = QFont(settings.font_family) if settings.font_family else QFont(QGuiApplication.font())
        font.setPixelSize(max(12, round(settings.font_size * scale * size_ratio)))
        font.setWeight(QFont.Weight(settings.font_weight))
        metrics = QFontMetricsF(font)
        lines = visible_lines(wrap_text(text, settings.max_chars, max_width - 36 * scale,
                                        metrics.horizontalAdvance), settings.max_lines)
        for line in lines:
            raw.append((shaped_path(line, font), QColor(color), metrics.height()))
    if not raw:
        return [], QSize(1, 1)
    width = min(max_width, max(280 if toolbar else 0,
                               math.ceil(max(path.boundingRect().width() for path, _, _ in raw) + 36 * scale)))
    y = 44.0 if toolbar else 0.0
    rows = []
    for path, color, height in raw:
        row_width = min(width, path.boundingRect().width() + 30 * scale)
        rect = QRectF((width - row_width) / 2, y, row_width, height + 12 * scale)
        centered = path.translated((width - path.boundingRect().width()) / 2,
                                   y + (rect.height() - path.boundingRect().height()) / 2)
        rows.append(TextRow(centered, rect, color))
        y += rect.height() + 5 * scale
    return rows, QSize(width, math.ceil(y + 8 * scale))


def paint_rows(painter: QPainter, rows: list[TextRow], settings: Settings,
               glass: bool = False, scale: float = 1) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for row in rows:
        if settings.background != "none":
            alpha = int(settings.background_opacity * 255 / 100)
            if glass:
                alpha = max(12, alpha // 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(8, 13, 20, alpha))
            painter.drawRoundedRect(row.rect, 7 * scale, 7 * scale)
            if settings.background == "glass":
                painter.setPen(QPen(QColor(255, 255, 255, 35), 0.6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(row.rect.adjusted(0.5, 0.5, -0.5, -0.5), 7 * scale, 7 * scale)
        if settings.shadow:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.drawPath(row.path.translated(1.5 * scale, 2.5 * scale))
        if settings.outline_width:
            painter.strokePath(row.path, QPen(QColor(settings.outline_color), settings.outline_width * 2 * scale,
                                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        # Fill after the stroke so the outline never covers narrow glyph stems.
        painter.fillPath(row.path, row.color)


class SubtitleOverlay(QWidget):
    settings_requested = Signal()
    font_delta = Signal(int)
    lock_requested = Signal()
    mode_requested = Signal()
    dragged = Signal(float, float)
    obstruction = Signal(bool)

    def __init__(self, settings: Settings) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setMouseTracking(True)
        self.settings = settings
        self.original, self.translation = "", ""
        self.rows: list[TextRow] = []
        self.wanted = True
        self._drag_offset: QPoint | None = None
        self._blocked = False
        self.native = NativeWindow(self)
        self.toolbar = QFrame(self)
        self.toolbar.setObjectName("overlayToolbar")
        self.toolbar.setStyleSheet("QFrame#overlayToolbar{background:#17232D;border:1px solid #3D515D;border-radius:9px;}"
                                   "QPushButton{color:#E7F1F1;background:transparent;border:0;padding:4px 7px;font-size:12px;}"
                                   "QPushButton:hover{background:#30474E;border-radius:5px;}")
        row = QHBoxLayout(self.toolbar)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(0)
        for label, callback in (("双语", self.mode_requested.emit), ("A−", lambda: self.font_delta.emit(-2)),
                                ("A+", lambda: self.font_delta.emit(2)),
                                ("锁定", self.lock_requested.emit), ("设置", self.settings_requested.emit)):
            button = QPushButton(label)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(callback)
            row.addWidget(button)
        self.toolbar.hide()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, settings.click_through)

    def set_text(self, original: str, translation: str) -> None:
        self.original, self.translation = original, translation
        self.refresh()

    def set_wanted(self, wanted: bool) -> None:
        self.wanted = wanted
        self.refresh()

    def set_locked(self, locked: bool) -> None:
        self.toolbar.hide()
        self.native.glass(False, [], 0)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, locked)
        self.native = NativeWindow(self)
        self.refresh()

    def _regions(self, screen) -> list[Rect]:
        area = screen.availableGeometry()
        return [Rect(area.x() + x * area.width(), area.y() + y * area.height(),
                     w * area.width(), h * area.height())
                for x, y, w, h in self.settings.safe_regions.get(screen_key(screen), [])]

    def refresh(self) -> None:
        screen = selected_screen(self.settings)
        if screen is None:
            self.hide()
            return
        area = screen.availableGeometry()
        ratio = 0.32 if self.settings.position in {"left", "right"} else 0.86
        max_width = max(120, int(area.width() * ratio))
        self.rows, size = build_rows(self.settings, self.original, self.translation, max_width)
        bounds = Rect(area.x() + 12, area.y() + 12, area.width() - 24, area.height() - 24)
        preferred = preferred_position(bounds, (size.width(), size.height()), self.settings.position,
                                       (self.settings.custom_x, self.settings.custom_y))
        location = place_subtitle(bounds, (size.width(), size.height()), preferred, self._regions(screen))
        blocked = location is None and bool(self.rows)
        if blocked != self._blocked:
            self._blocked = blocked
            self.obstruction.emit(blocked)
        if not self.wanted or not self.rows or location is None:
            self.hide()
            return
        self.setGeometry(round(location.x), round(location.y), size.width(), size.height())
        self.toolbar.setGeometry(max(0, (size.width() - 280) // 2), 2, min(280, size.width()), 34)
        self.show()
        self.native.configure()
        self._glass()
        self.update()

    def _glass(self) -> None:
        rectangles = [row.rect.toAlignedRect() for row in self.rows]
        if self.toolbar.isVisible():
            rectangles.append(self.toolbar.geometry())
        self.native.glass(self.settings.background == "glass", rectangles, self.settings.background_opacity)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        paint_rows(painter, self.rows, self.settings, self.native.glass_active)

    def enterEvent(self, event) -> None:
        if not self.settings.click_through:
            self.toolbar.show()
            self._glass()

    def leaveEvent(self, event) -> None:
        if self._drag_offset is None:
            self.toolbar.hide()
            self._glass()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is None:
            return
        area = selected_screen(self.settings).availableGeometry()
        desired = event.globalPosition().toPoint() - self._drag_offset
        location = place_subtitle(Rect(area.x() + 12, area.y() + 12, area.width() - 24, area.height() - 24),
                                  (self.width(), self.height()), (desired.x(), desired.y()),
                                  self._regions(selected_screen(self.settings)))
        if location:
            self.move(round(location.x), round(location.y))

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            area = selected_screen(self.settings).availableGeometry()
            center = self.geometry().center()
            self.dragged.emit(max(0, min(1, (center.x() - area.x()) / area.width())),
                              max(0, min(1, (center.y() - area.y()) / area.height())))


class SafetyPicker(QWidget):
    finished = Signal(object)  # list of normalized rectangles, or None on cancel

    def __init__(self, screen, existing: list[list[float]]) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(screen.availableGeometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.rectangles = [QRectF(x * self.width(), y * self.height(), w * self.width(), h * self.height())
                           for x, y, w, h in existing]
        self.start: QPointF | None = None
        self.current: QRectF | None = None
        self._completed = False

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(4, 10, 20, 85))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#FFFFFF"))
        font = QFont(self.font())
        font.setPixelSize(18)
        painter.setFont(font)
        painter.fillRect(QRect(20, 20, min(880, self.width() - 40), 72), QColor(9, 22, 32, 235))
        painter.drawText(QRect(38, 28, self.width() - 76, 55), Qt.AlignmentFlag.AlignVCenter,
                         "拖拽框选需要保护的区域（最多 8 个）\nEnter 保存 · Esc 取消 · 右键删除区域")
        for index, rectangle in enumerate(self.rectangles + ([self.current] if self.current else []), 1):
            painter.setPen(QPen(QColor("#71E7BA"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(67, 221, 166, 30))
            painter.drawRoundedRect(rectangle, 5, 5)
            painter.drawText(rectangle.adjusted(8, 8, -8, -8), Qt.AlignmentFlag.AlignTop, str(index))

    def mousePressEvent(self, event) -> None:
        point = event.position()
        if event.button() == Qt.MouseButton.RightButton:
            self.rectangles = [rect for rect in self.rectangles if not rect.contains(point)]
        elif event.button() == Qt.MouseButton.LeftButton and len(self.rectangles) < 8:
            self.start = point
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.start is not None:
            self.current = QRectF(self.start, event.position()).normalized().intersected(QRectF(self.rect()))
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self.current and self.current.width() >= 12 and self.current.height() >= 12:
            self.rectangles.append(self.current)
        self.start = None
        self.current = None
        self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self._completed = True
            self.finished.emit([[r.x() / self.width(), r.y() / self.height(),
                                 r.width() / self.width(), r.height() / self.height()] for r in self.rectangles])
            self.close()
        elif event.key() == Qt.Key.Key_Escape:
            self._completed = True
            self.finished.emit(None)
            self.close()

    def closeEvent(self, event) -> None:
        if not self._completed:
            self._completed = True
            self.finished.emit(None)
        event.accept()
