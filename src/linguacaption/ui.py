from __future__ import annotations

import html
import math
import platform
import time
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path

import psutil
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import LANGUAGES, Settings, save_settings
from .core.chinese import simplified
from .core.presentation import CaptionPresenter
from .domain import Caption
from .engine import Engine
from .native.hotkeys import Hotkeys
from .overlay import SafetyPicker, SubtitleOverlay, build_rows, paint_rows, screen_key, selected_screen
from .runtime import is_bundled, models_ready

SAMPLE_ORIGINAL = "There is a whole world waiting to be understood."
SAMPLE_TRANSLATION = "让每一种语言，都触手可及。"

STYLE = """
QWidget {color:#E5EEEE; font-size:13px;}
QMainWindow, QWidget#main {background:#10171F;}
QFrame#sidebar {background:#0C1219; border-right:1px solid #24303A;}
QLabel#brand {font-size:19px;font-weight:700;color:#F3FAF8;}
QLabel#mark {background:#8CE7C3;color:#0E3129;border-radius:12px;font-size:18px;font-weight:800;}
QLabel#title {font-size:27px;font-weight:700;color:#F2F7F8;}
QLabel#subtitle, QLabel#muted {color:#92A4AF;}
QLabel#section {font-size:15px;font-weight:600;color:#F0F6F7;}
QLabel#eyebrow {color:#88D8BD;font-size:11px;font-weight:700;}
QLabel#badge {color:#9DEACD;background:#1B332F;border:1px solid #31594F;border-radius:11px;padding:5px 12px;}
QFrame#card {background:#18222D;border:1px solid #2B3946;border-radius:14px;}
QPushButton {background:#25333F;border:1px solid #3A4B59;border-radius:8px;padding:8px 13px;color:#E2ECEE;}
QPushButton:hover {background:#304551;border-color:#608A88;}
QPushButton:disabled {color:#657782;background:#1D2933;}
QPushButton#primary {background:#8CE7C3;border-color:#8CE7C3;color:#102F27;font-weight:700;padding:12px 22px;}
QPushButton#primary:hover {background:#B1F6DA;}
QPushButton#nav {text-align:left;padding:12px 14px;background:transparent;border:0;color:#93A6B3;}
QPushButton#nav:checked {background:#19352F;color:#A2F1D4;border-left:3px solid #8CE7C3;border-radius:6px;}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QFontComboBox {
 background:#111B24;border:1px solid #364855;border-radius:7px;padding:7px 9px;min-height:20px;}
QComboBox:focus, QLineEdit:focus {border-color:#8CE7C3;}
QComboBox::drop-down {border:0;width:22px;}
QComboBox QAbstractItemView {background:#1A2934;selection-background-color:#2E5148;padding:5px;}
QCheckBox {spacing:9px;color:#BCCDD4;padding:4px 0;}
QCheckBox::indicator {width:16px;height:16px;border:1px solid #55717C;border-radius:4px;background:#14212A;}
QCheckBox::indicator:checked {background:#8CE7C3;border-color:#8CE7C3;}
QSlider::groove:horizontal {height:5px;background:#32434F;border-radius:2px;}
QSlider::sub-page:horizontal {background:#8CE7C3;border-radius:2px;}
QSlider::handle:horizontal {width:14px;margin:-5px 0;background:#B0F3D7;border-radius:7px;}
QTextBrowser, QPlainTextEdit {background:#111B24;border:1px solid #2B3E4B;border-radius:8px;padding:10px;color:#C3D2D9;}
QScrollArea {border:0;background:transparent;}
QScrollBar:vertical {background:#111B24;width:8px;}
QScrollBar::handle:vertical {background:#42535F;border-radius:4px;min-height:30px;}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height:0;}
QProgressBar {border:0;background:#2B3B47;border-radius:3px;height:6px;}
QProgressBar::chunk {background:#8CE7C3;border-radius:3px;}
QToolTip {background:#263946;color:#E7F6F2;border:1px solid #4F736A;padding:6px;}
"""


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(14)
    return frame, layout


class CaptionPreview(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.original, self.translation = SAMPLE_ORIGINAL, SAMPLE_TRANSLATION
        self.setMinimumSize(300, 230)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 10, 10)
        painter.setClipPath(clip)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor("#142532"))
        gradient.setColorAt(0.65, QColor("#446A71"))
        gradient.setColorAt(1, QColor("#263A4A"))
        painter.fillRect(self.rect(), gradient)
        painter.setBrush(QColor("#A3C7B4"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(self.width() * .75, self.height() * .27), 22, 22)
        for phase, color, level in ((0, "#314F5B", .50), (1.4, "#213C4A", .67), (3, "#132B38", .82)):
            path = QPainterPath()
            path.moveTo(0, self.height())
            for x in range(0, self.width() + 8, 8):
                y = (level + .10 * math.sin(x / 80 + phase) + .04 * math.cos(x / 28)) * self.height()
                path.lineTo(x, y)
            path.lineTo(self.width(), self.height())
            path.closeSubpath()
            painter.fillPath(path, QColor(color))
        painter.setPen(QColor("#D3E2E3"))
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        painter.setFont(font)
        painter.drawText(17, 25, "CAPTION PREVIEW")
        screen = selected_screen(self.settings)
        for x, y, w, h in self.settings.safe_regions.get(screen_key(screen), []) if screen else []:
            painter.setPen(QPen(QColor(140, 231, 195, 120), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(140, 231, 195, 15))
            painter.drawRoundedRect(QRectF(x * self.width(), y * self.height(), w * self.width(), h * self.height()), 5, 5)
        rows, size = build_rows(self.settings, self.original, self.translation, self.width() - 28,
                               scale=.66, toolbar=False)
        painter.translate((self.width() - size.width()) / 2, max(40, self.height() - size.height() - 16))
        paint_rows(painter, rows, self.settings, scale=.66)


class MainWindow(QMainWindow):
    devices_ready = Signal(object)
    closed = Signal()

    def __init__(self, settings: Settings, config_path: Path, demo: bool = False,
                 register_hotkeys: bool = True) -> None:
        super().__init__()
        self.settings, self.config_path = settings, config_path
        self._engine: Engine | None = None
        self._restart = False
        self._last_error = ""
        self._last_caption: Caption | None = None
        self._presenter = CaptionPresenter(settings)
        self._metrics_at = 0.0
        self._style_preview = False
        self._picker = None
        self._history: OrderedDict[int, Caption] = OrderedDict()
        self._process = psutil.Process()
        self._process.cpu_percent()
        self.overlay = SubtitleOverlay(settings)
        self.overlay.settings_requested.connect(self.show_settings)
        self.overlay.font_delta.connect(self.change_font)
        self.overlay.lock_requested.connect(self.toggle_lock)
        self.overlay.mode_requested.connect(self.cycle_mode)
        self.overlay.dragged.connect(self._dragged)
        self.overlay.obstruction.connect(self._obstructed)
        self.setWindowTitle("LinguaCaption · 随声字幕")
        self.resize(1180, 840)
        self.setMinimumSize(1000, 720)
        self.setStyleSheet(STYLE)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save)
        self._build(demo)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)
        self.hotkeys = Hotkeys(QApplication.instance())
        self.hotkeys.action.connect(self._hotkey, Qt.ConnectionType.QueuedConnection)
        if register_hotkeys:
            errors = self.hotkeys.register()
            if errors:
                self.status_message.setText(self.status_message.text() + "\n" + "；".join(errors))
        self.devices_ready.connect(self._set_devices, Qt.ConnectionType.QueuedConnection)

    def _build(self, demo: bool) -> None:
        root = QWidget()
        root.setObjectName("main")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(184)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 30, 18, 24)
        brand = QHBoxLayout()
        mark = label("LC", "mark")
        mark.setFixedSize(42, 42)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(mark)
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(1)
        brand_copy.addWidget(label("随声字幕", "brand"))
        english = label("LinguaCaption", "muted")
        english.setStyleSheet("font-size:10px;")
        brand_copy.addWidget(english)
        brand.addLayout(brand_copy)
        side.addLayout(brand)
        side.addSpacing(32)
        side.addWidget(label("工作空间", "muted"))
        self.nav = []
        for index, title in enumerate(("01   字幕工作台", "Aa   样式与位置", "03   模型与性能")):
            button = QPushButton(title)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.navigate(i))
            side.addWidget(button)
            self.nav.append(button)
        side.addStretch()
        side.addWidget(label("●  本地离线处理", "eyebrow"))
        side.addWidget(label("音频保留在内存中\n不使用麦克风", "muted", True))
        side.addSpacing(14)
        side.addWidget(label(f"v{__version__}  /  Desktop", "muted"))
        layout.addWidget(sidebar)
        body = QVBoxLayout()
        body.setContentsMargins(30, 28, 30, 20)
        body.setSpacing(20)
        header = QHBoxLayout()
        title = QVBoxLayout()
        self.page_title = label("实时双语字幕", "title")
        title.addWidget(self.page_title)
        title.addWidget(label("系统音频内录  /  本地识别与翻译  /  桌面悬浮", "subtitle"))
        header.addLayout(title)
        header.addStretch()
        header.addWidget(label("LOCAL FIRST", "badge"))
        body.addLayout(header)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._session_page(demo))
        self.pages.addWidget(self._style_page())
        self.pages.addWidget(self._model_page())
        body.addWidget(self.pages, 1)
        footer = QHBoxLayout()
        self.cpu_label = label("CPU —  ·  内存 —", "muted")
        footer.addWidget(self.cpu_label)
        footer.addStretch()
        footer.addWidget(label("Ctrl + Alt + S 显隐字幕   ·   Ctrl + Alt + K 锁定/解锁", "muted"))
        body.addLayout(footer)
        layout.addLayout(body, 1)
        self.navigate(0)

    def navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.page_title.setText(("实时双语字幕", "字幕样式与位置", "本地模型与性能")[index])
        for i, button in enumerate(self.nav):
            button.setChecked(i == index)

    def _language_combo(self, current: str, auto: bool = False) -> QComboBox:
        combo = QComboBox()
        if auto:
            combo.addItem("自动检测", "auto")
        for code, name in LANGUAGES.items():
            combo.addItem(name, code)
        combo.setCurrentIndex(combo.findData(current))
        return combo

    def _session_page(self, demo: bool) -> QWidget:
        page, layout = self._scroll_page()
        layout.setSpacing(16)
        state, state_layout = card()
        top = QHBoxLayout()
        copy = QVBoxLayout()
        self.state_label = label("●  准备就绪", "section")
        copy.addWidget(self.state_label)
        message = ("离线模型已就绪。播放视频后点击「开始捕获」，即可显示实时字幕。"
                   if models_ready(self.settings) else "首次使用请先在「模型与性能」配置本地模型，也可勾选演示模式体验字幕。")
        self.status_message = label(message, "muted", True)
        copy.addWidget(self.status_message)
        top.addLayout(copy, 1)
        self.start_button = QPushButton("开始捕获")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.toggle_session)
        top.addWidget(self.start_button)
        state_layout.addLayout(top)
        self.demo_check = QCheckBox("演示模式 · 英文→中文示例，无音频采集")
        self.demo_check.setChecked(demo)
        state_layout.addWidget(self.demo_check)
        layout.addWidget(state)
        columns = QHBoxLayout()
        columns.setSpacing(16)
        inputs, inputs_layout = card()
        inputs_layout.addWidget(label("01   声音与语言", "eyebrow"))
        form = QFormLayout()
        form.setVerticalSpacing(14)
        self.audio_combo = QComboBox()
        self.audio_combo.addItem("系统默认输出 · 内录", "default")
        if self.settings.audio_device != "default":
            self.audio_combo.addItem("已保存的输出设备", self.settings.audio_device)
            self.audio_combo.setCurrentIndex(1)
        self.audio_combo.currentIndexChanged.connect(lambda: self._set_pipeline("audio_device", self.audio_combo.currentData()))
        self.refresh_device_button = QPushButton("刷新音源")
        self.refresh_device_button.clicked.connect(self.refresh_devices)
        audio_row = QHBoxLayout()
        audio_row.addWidget(self.audio_combo, 1)
        audio_row.addWidget(self.refresh_device_button)
        form.addRow("音源", audio_row)
        self.source_combo = self._language_combo(self.settings.source, True)
        self.source_combo.currentIndexChanged.connect(lambda: self._set_pipeline("source", self.source_combo.currentData()))
        form.addRow("识别语言", self.source_combo)
        self.target_combo = self._language_combo(self.settings.target)
        self.target_combo.currentIndexChanged.connect(lambda: self._set_pipeline("target", self.target_combo.currentData()))
        form.addRow("目标语言", self.target_combo)
        swap = QPushButton("交换语言   Ctrl + Alt + L")
        swap.clicked.connect(self.swap_languages)
        form.addRow("", swap)
        self.mode_combo = QComboBox()
        for text, mode in (("双语对照", "bilingual"), ("仅原文", "original"), ("仅译文", "translation")):
            self.mode_combo.addItem(text, mode)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(self.settings.mode))
        self.mode_combo.currentIndexChanged.connect(self._change_mode)
        form.addRow("显示模式", self.mode_combo)
        preset = QPushButton("中文实时字幕 · 边说边出字")
        preset.clicked.connect(self.mandarin_preset)
        form.addRow("快捷设置", preset)
        inputs_layout.addLayout(form)
        inputs_layout.addStretch()
        inputs_layout.addWidget(label("语言或模式变更会重启当前会话。\n自动检测可能需要更长的语音上下文。", "muted", True))
        columns.addWidget(inputs, 1)
        preview_card, preview_layout = card()
        preview_head = QHBoxLayout()
        preview_head.addWidget(label("02   字幕预览", "eyebrow"))
        preview_head.addStretch()
        self.preview_badge = label("示例文本", "muted")
        preview_head.addWidget(self.preview_badge)
        preview_layout.addLayout(preview_head)
        self.preview = CaptionPreview(self.settings)
        preview_layout.addWidget(self.preview, 1)
        actions = QHBoxLayout()
        self.preview_button = QPushButton("预览悬浮字幕")
        self.preview_button.clicked.connect(self.preview_overlay)
        actions.addWidget(self.preview_button)
        self.visibility_button = QPushButton("隐藏字幕")
        self.visibility_button.clicked.connect(self.toggle_visibility)
        actions.addWidget(self.visibility_button)
        preview_layout.addLayout(actions)
        preview_layout.addWidget(label("预览图用于查看文字样式；位置与避让请在实际屏幕预览。", "muted", True))
        columns.addWidget(preview_card, 1)
        layout.addLayout(columns, 1)
        metrics = QHBoxLayout()
        self.metric_values = {}
        for key, title in (("asr", "识别耗时"), ("translation", "翻译耗时"), ("lag", "字幕滞后 · 估算")):
            metric, content = card()
            content.setContentsMargins(18, 12, 18, 12)
            content.setSpacing(4)
            content.addWidget(label(title, "muted"))
            value = label("—", "section")
            self.metric_values[key] = value
            content.addWidget(value)
            metrics.addWidget(metric)
        layout.addLayout(metrics)
        history_card, history_layout = card()
        history_layout.setContentsMargins(18, 14, 18, 14)
        history_layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(label("当前会话", "section"))
        heading.addStretch()
        export = QPushButton("导出文本")
        export.clicked.connect(self.export_history)
        heading.addWidget(export)
        history_layout.addLayout(heading)
        self.history_view = QTextBrowser()
        self.history_view.setMinimumHeight(90)
        self.history_view.setMaximumHeight(140)
        self.history_view.setPlaceholderText("识别文字和译文会显示在这里。仅保留最近 60 条，不自动保存。")
        history_layout.addWidget(self.history_view)
        self.level_meter = QProgressBar()
        self.level_meter.setRange(0, 100)
        self.level_meter.setTextVisible(False)
        self.level_meter.setFixedHeight(5)
        history_layout.addWidget(self.level_meter)
        layout.addWidget(history_card)
        return page

    def _scroll_page(self) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("scrollBody")
        body.setStyleSheet("QWidget#scrollBody{background:transparent;}")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(16)
        scroll.setWidget(body)
        return scroll, layout

    def _spin(self, field: str, minimum: int, maximum: int, step: int = 1) -> QSpinBox:
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setSingleStep(step)
        control.setValue(getattr(self.settings, field))
        control.valueChanged.connect(lambda value: self._set_style(field, value))
        return control

    def _style_page(self) -> QWidget:
        page, layout = self._scroll_page()
        appearance, content = card()
        content.addWidget(label("文字与背景", "section"))
        form = QFormLayout()
        form.setVerticalSpacing(14)
        font = QFontComboBox()
        font.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)
        font.setCurrentFont(QFont(self.settings.font_family) if self.settings.font_family
                            else QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
        font.currentFontChanged.connect(lambda value: self._set_style("font_family", value.family()))
        font_row = QHBoxLayout()
        font_row.addWidget(font)
        system_font = QPushButton("使用系统字体")
        def restore_system_font() -> None:
            font.blockSignals(True)
            font.setCurrentFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
            font.blockSignals(False)
            self._set_style("font_family", "")
        system_font.clicked.connect(restore_system_font)
        font_row.addWidget(system_font)
        form.addRow("字体 · 默认跟随系统", font_row)
        self.font_size_spin = self._spin("font_size", 16, 80, 2)
        form.addRow("字号 · 逻辑像素", self.font_size_spin)
        weight = QComboBox()
        for text, value in (("常规 400", 400), ("中等 500", 500), ("半粗 600", 600), ("加粗 700", 700)):
            weight.addItem(text, value)
        weight.setCurrentIndex(max(0, weight.findData(self.settings.font_weight)))
        weight.currentIndexChanged.connect(lambda: self._set_style("font_weight", weight.currentData()))
        form.addRow("字重", weight)
        colors = QHBoxLayout()
        for title, field in (("原文", "original_color"), ("译文", "translation_color"), ("描边", "outline_color")):
            button = QPushButton(title + "  " + getattr(self.settings, field))
            button.clicked.connect(lambda checked=False, name=field, b=button, t=title: self._choose_color(name, b, t))
            colors.addWidget(button)
        form.addRow("颜色", colors)
        outline = QDoubleSpinBox()
        outline.setRange(0, 6)
        outline.setSingleStep(.5)
        outline.setValue(self.settings.outline_width)
        outline.valueChanged.connect(lambda value: self._set_style("outline_width", value))
        form.addRow("描边粗细", outline)
        shadow = QCheckBox("为文字添加阴影")
        shadow.setChecked(self.settings.shadow)
        shadow.toggled.connect(lambda value: self._set_style("shadow", value))
        form.addRow("阴影", shadow)
        background = QComboBox()
        for text, value in (("半透明黑底", "dark"), ("无背景", "none"), ("磨砂玻璃 · 需要系统合成支持", "glass")):
            background.addItem(text, value)
        background.setCurrentIndex(background.findData(self.settings.background))
        background.currentIndexChanged.connect(lambda: self._set_style("background", background.currentData()))
        form.addRow("背景", background)
        opacity = QSlider(Qt.Orientation.Horizontal)
        opacity.setRange(0, 95)
        opacity.setValue(self.settings.background_opacity)
        opacity.valueChanged.connect(lambda value: self._set_style("background_opacity", value))
        form.addRow("背景不透明度", opacity)
        form.addRow("每行最多字数", self._spin("max_chars", 8, 80))
        form.addRow("每种语言最多行数", self._spin("max_lines", 1, 4))
        for title, field, low, high in (("停顿后保留", "subtitle_timeout_ms", 2, 30),):
            seconds = QDoubleSpinBox()
            seconds.setRange(low, high)
            seconds.setSingleStep(.5)
            seconds.setSuffix(" 秒")
            seconds.setValue(getattr(self.settings, field) / 1000)
            seconds.valueChanged.connect(lambda value, name=field: self._set_style(name, round(value * 1000)))
            form.addRow(title, seconds)
        content.addLayout(form)
        content.addWidget(label("默认白色字、系统字体和黑色阴影。中文原文与译文统一为简体。\n新语音及时替换；仅在停顿后保留文字，不排队等待。字幕过长时完整内容保留在会话记录中。\n磨砂不可用时自动使用半透明黑底。", "muted", True))
        layout.addWidget(appearance)
        position, position_layout = card()
        position_layout.addWidget(label("位置与保护区域", "section"))
        form = QFormLayout()
        self.position_combo = QComboBox()
        for text, value in (("底部居中", "bottom"), ("顶部居中", "top"), ("左侧栏", "left"),
                            ("右侧栏", "right"), ("自由拖拽位置", "custom")):
            self.position_combo.addItem(text, value)
        self.position_combo.setCurrentIndex(self.position_combo.findData(self.settings.position))
        self.position_combo.currentIndexChanged.connect(lambda: self._set_style("position", self.position_combo.currentData()))
        form.addRow("预设位置", self.position_combo)
        self.screen_combo = QComboBox()
        self._populate_screens()
        self.screen_combo.currentIndexChanged.connect(self._screen_changed)
        QApplication.instance().screenAdded.connect(lambda screen: self._screens_changed())
        QApplication.instance().screenRemoved.connect(lambda screen: self._screens_changed())
        form.addRow("显示屏", self.screen_combo)
        self.lock_check = QCheckBox("锁定位置，鼠标穿透（Ctrl + Alt + K 解锁；开始捕获时自动解锁）")
        self.lock_check.setChecked(self.settings.click_through)
        self.lock_check.toggled.connect(self._lock_changed)
        form.addRow("观看模式", self.lock_check)
        position_layout.addLayout(form)
        self.safe_label = label("", "muted")
        position_layout.addWidget(self.safe_label)
        actions = QHBoxLayout()
        select = QPushButton("在屏幕上框选保护区域")
        select.clicked.connect(self.pick_safety)
        clear = QPushButton("清空本屏保护区域")
        clear.clicked.connect(self.clear_safety)
        preview = QPushButton("预览悬浮字幕")
        preview.clicked.connect(self.preview_overlay)
        actions.addWidget(select)
        actions.addWidget(clear)
        actions.addWidget(preview)
        position_layout.addLayout(actions)
        position_layout.addWidget(label("在播放画面上框选人脸、画面原字幕等位置，系统自动选择最近的可用区域。\n保护区随屏幕保存；视频移动后请重新框选。没有足够空间时字幕会隐藏。", "muted", True))
        layout.addWidget(position)
        self._update_safe_label()
        layout.addStretch()
        return page

    def _model_page(self) -> QWidget:
        page, layout = self._scroll_page()
        models, content = card()
        content.addWidget(label("离线模型", "section"))
        content.addWidget(label("运行时仅加载完整的本地模型目录。模型准备命令会访问网络，字幕会话不会自动下载。", "muted", True))
        form = QFormLayout()
        self.backend_combo = QComboBox()
        for title, value in (("自动：中文流式 / 其他语言 Whisper", "auto"),
                             ("Whisper 多语言", "whisper"), ("中文流式 Paraformer", "paraformer")):
            self.backend_combo.addItem(title, value)
        self.backend_combo.setCurrentIndex(self.backend_combo.findData(self.settings.asr_backend))
        self.backend_combo.currentIndexChanged.connect(
            lambda: self._set_pipeline("asr_backend", self.backend_combo.currentData()))
        form.addRow("识别引擎", self.backend_combo)
        self.model_paths = {}
        for title, field in (("中文流式模型", "streaming_model"), ("Whisper 识别模型", "asr_model"),
                             ("M2M100 翻译模型", "translation_model")):
            row = QHBoxLayout()
            control = QLineEdit(getattr(self.settings, field))
            control.editingFinished.connect(lambda name=field, widget=control: self._set_pipeline(name, widget.text().strip()))
            self.model_paths[field] = control
            choose = QPushButton("选择目录")
            choose.clicked.connect(lambda checked=False, name=field: self._choose_directory(name))
            row.addWidget(control, 1)
            row.addWidget(choose)
            form.addRow(title, row)
        content.addLayout(form)
        if is_bundled():
            content.addWidget(label("完整软件内置离线识别和翻译模型，无需安装 Python。可直接开始捕获，也可以在上方选择其他已准备的模型。", "muted", True))
        else:
            content.addWidget(label("准备命令（在项目根目录运行）", "eyebrow"))
            commands = QPlainTextEdit("python -m pip install -e '.[prepare]'\npython scripts/prepare_mandarin.py\npython scripts/prepare_models.py asr --size base\npython scripts/prepare_models.py translation")
            commands.setReadOnly(True)
            commands.setFixedHeight(95)
            content.addWidget(commands)
        diagnose = QPushButton("检查模型文件与平台能力")
        diagnose.clicked.connect(self.diagnose)
        content.addWidget(diagnose)
        self.diagnostic = label("", "muted", True)
        content.addWidget(self.diagnostic)
        layout.addWidget(models)
        performance, content = card()
        content.addWidget(label("性能与分段", "section"))
        content.addWidget(label("中文流式模型连续接收音频；Whisper 的更新间隔与上下文设置仅用于 Whisper。500 ms / 95% 按实测验收。", "muted", True))
        form = QFormLayout()
        device = QComboBox()
        device.addItem("CPU", "cpu")
        device.addItem("NVIDIA CUDA（需匹配 CUDA/cuDNN）", "cuda")
        device.setCurrentIndex(device.findData(self.settings.device))
        device.currentIndexChanged.connect(lambda: self._set_pipeline("device", device.currentData()))
        form.addRow("Whisper 计算设备", device)
        compute = QComboBox()
        for value in ("int8", "float32", "float16", "int8_float16"):
            compute.addItem(value, value)
        compute.setCurrentIndex(compute.findData(self.settings.compute_type))
        compute.currentIndexChanged.connect(lambda: self._set_pipeline("compute_type", compute.currentData()))
        form.addRow("Whisper 精度", compute)
        for title, name, low, high, step in (
            ("中文流式线程", "streaming_threads", 1, 16, 1), ("Whisper CPU 线程", "asr_threads", 1, 16, 1), ("翻译 CPU 线程", "translation_threads", 1, 8, 1),
            ("更新间隔 ms", "update_ms", 200, 2000, 100), ("首次上下文 ms", "min_audio_ms", 320, 2000, 20),
            ("停顿确认 ms", "endpoint_ms", 200, 1200, 20), ("最长语句 ms", "max_utterance_ms", 2000, 12000, 1000),
        ):
            control = QSpinBox()
            control.setRange(low, high)
            control.setSingleStep(step)
            control.setValue(getattr(self.settings, name))
            control.valueChanged.connect(lambda value, field=name: self._set_pipeline(field, value))
            form.addRow(title, control)
        content.addLayout(form)
        content.addWidget(label("中文流式使用 CPU INT8，默认 4 线程；仅原文及同语言字幕跳过翻译模型。Mac 当前使用 CPU，不会将 MPS 当成 CUDA。\n建议先选定源语言，使用 base/small 模型，结合真实视频调整。设置变更会重启会话。", "muted", True))
        layout.addWidget(performance)
        layout.addStretch()
        return page

    def _set_style(self, field: str, value) -> None:
        setattr(self.settings, field, value)
        self._save_timer.start(350)
        self.preview.update()
        self.overlay.refresh()

    def _set_pipeline(self, field: str, value) -> None:
        if getattr(self.settings, field) == value:
            return
        setattr(self.settings, field, value)
        self._save_timer.start(350)
        if self._engine:
            self._restart = True
            self._stop_session("正在应用新设置…")

    def mandarin_preset(self) -> None:
        for widget in (self.source_combo, self.target_combo, self.mode_combo, self.backend_combo):
            widget.blockSignals(True)
        self.settings.source = self.settings.target = "zh"
        self.settings.mode = "original"
        self.settings.asr_backend = "auto"
        self.source_combo.setCurrentIndex(self.source_combo.findData("zh"))
        self.target_combo.setCurrentIndex(self.target_combo.findData("zh"))
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("original"))
        self.backend_combo.setCurrentIndex(self.backend_combo.findData("auto"))
        for widget in (self.source_combo, self.target_combo, self.mode_combo, self.backend_combo):
            widget.blockSignals(False)
        self._clear_subtitles()
        self._save_timer.start(350)
        self.preview.update()
        if self._engine:
            self._restart = True
            self._stop_session("正在切换中文实时字幕…")

    def _change_mode(self) -> None:
        self._set_pipeline("mode", self.mode_combo.currentData())
        self.preview.update()
        self.overlay.refresh()

    def cycle_mode(self) -> None:
        self.mode_combo.setCurrentIndex((self.mode_combo.currentIndex() + 1) % self.mode_combo.count())

    def _choose_color(self, field: str, button: QPushButton, title: str) -> None:
        color = QColorDialog.getColor(QColor(getattr(self.settings, field)), self, title)
        if color.isValid():
            self._set_style(field, color.name().upper())
            button.setText(title + "  " + color.name().upper())

    def _choose_directory(self, field: str) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择完整模型目录", self.model_paths[field].text())
        if path:
            self.model_paths[field].setText(path)
            self._set_pipeline(field, path)

    def _populate_screens(self) -> None:
        self.screen_combo.blockSignals(True)
        self.screen_combo.clear()
        for index, screen in enumerate(QApplication.screens(), 1):
            area = screen.availableGeometry()
            self.screen_combo.addItem(f"{index} · {screen.name() or '显示屏'}  ({area.width()} × {area.height()})", screen.name())
        self.screen_combo.setCurrentIndex(max(0, self.screen_combo.findData(self.settings.screen_name)))
        self.screen_combo.blockSignals(False)

    def _screens_changed(self) -> None:
        if self._picker:
            self._picker.close()
        self._populate_screens()
        self._screen_changed()

    def _screen_changed(self) -> None:
        self._set_style("screen_name", self.screen_combo.currentData() or "")
        self._update_safe_label()

    def _update_safe_label(self) -> None:
        screen = selected_screen(self.settings)
        count = len(self.settings.safe_regions.get(screen_key(screen), [])) if screen else 0
        self.safe_label.setText(f"本屏已设置 {count} / 8 个保护区域")

    def _lock_changed(self, locked: bool) -> None:
        self.settings.click_through = locked
        self.overlay.set_locked(locked)
        self._save_timer.start(350)

    def toggle_lock(self) -> None:
        self.lock_check.setChecked(not self.lock_check.isChecked())

    def _dragged(self, x: float, y: float) -> None:
        self.settings.custom_x, self.settings.custom_y = x, y
        self.position_combo.setCurrentIndex(self.position_combo.findData("custom"))
        self._save_timer.start(350)

    def _obstructed(self, blocked: bool) -> None:
        if blocked:
            self.status_message.setText("保护区域内没有足够的字幕空间，已隐藏悬浮字幕；请缩小字号或调整保护区域。")

    def pick_safety(self) -> None:
        if self._picker:
            return
        screen = selected_screen(self.settings)
        key = screen_key(screen)
        self.overlay.hide()
        self.hide()
        self._picker = SafetyPicker(screen, self.settings.safe_regions.get(key, []))

        def finished(rectangles) -> None:
            if rectangles is not None:
                self.settings.safe_regions[key] = rectangles
                self._save_timer.start(350)
            self._picker = None
            self.show()
            self._update_safe_label()
            self.overlay.refresh()
            self.preview.update()
        self._picker.finished.connect(finished)
        self._picker.show()
        self._picker.activateWindow()
        self._picker.setFocus()

    def clear_safety(self) -> None:
        self.settings.safe_regions.pop(screen_key(selected_screen(self.settings)), None)
        self._set_style("safe_regions", self.settings.safe_regions)
        self._update_safe_label()

    def preview_overlay(self) -> None:
        if self._engine:
            self.toggle_visibility()
            return
        self._style_preview = not self._style_preview
        self.overlay.set_wanted(self._style_preview)
        self.overlay.set_text(SAMPLE_ORIGINAL if self._style_preview else "",
                              SAMPLE_TRANSLATION if self._style_preview else "")
        self.preview_button.setText("关闭悬浮预览" if self._style_preview else "预览悬浮字幕")
        self.visibility_button.setText("隐藏字幕" if self.overlay.wanted else "显示字幕")

    def toggle_visibility(self) -> None:
        self.overlay.set_wanted(not self.overlay.wanted)
        self.visibility_button.setText("隐藏字幕" if self.overlay.wanted else "显示字幕")

    def show_settings(self) -> None:
        self.navigate(1)
        self.showNormal()
        self.activateWindow()

    def change_font(self, delta: int) -> None:
        self.font_size_spin.setValue(max(16, min(80, self.settings.font_size + delta)))

    def _hotkey(self, action: str) -> None:
        {"toggle": self.toggle_visibility, "swap": self.swap_languages,
         "larger": lambda: self.change_font(2), "smaller": lambda: self.change_font(-2),
         "lock": self.toggle_lock}[action]()

    def swap_languages(self) -> None:
        source, target = self.settings.source, self.settings.target
        if source == "auto":
            source = self._last_caption.language if self._last_caption and self._last_caption.language in LANGUAGES else "en"
        self.source_combo.blockSignals(True)
        self.target_combo.blockSignals(True)
        self.source_combo.setCurrentIndex(self.source_combo.findData(target))
        self.target_combo.setCurrentIndex(self.target_combo.findData(source))
        self.source_combo.blockSignals(False)
        self.target_combo.blockSignals(False)
        self._set_pipeline("source", target)
        self._set_pipeline("target", source)

    def refresh_devices(self) -> None:
        if platform.system() != "Windows":
            self.status_message.setText("macOS 使用 ScreenCaptureKit 捕获系统声音，无需选择麦克风或虚拟声卡。")
            return
        import threading
        self.refresh_device_button.setEnabled(False)

        def run() -> None:
            try:
                from .audio import windows_outputs
                self.devices_ready.emit(windows_outputs())
            except Exception as error:
                self.devices_ready.emit(str(error))
        threading.Thread(target=run, daemon=True).start()

    def _set_devices(self, result) -> None:
        self.refresh_device_button.setEnabled(True)
        if isinstance(result, str):
            self.status_message.setText("无法读取输出设备：" + result)
            return
        current = self.settings.audio_device
        self.audio_combo.blockSignals(True)
        self.audio_combo.clear()
        self.audio_combo.addItem("系统默认输出 · 内录", "default")
        for identifier, name in result:
            self.audio_combo.addItem(name, identifier)
        index = self.audio_combo.findData(current)
        self.audio_combo.setCurrentIndex(max(0, index))
        self.audio_combo.blockSignals(False)
        if index < 0:
            self._set_pipeline("audio_device", "default")

    def toggle_session(self) -> None:
        if self._engine:
            self._restart = False
            self._stop_session("正在停止，等待当前模型计算结束…")
        else:
            self.start_session()

    def start_session(self) -> None:
        if self._engine:
            return
        self._last_error = ""
        self._restart = False
        self._history.clear()
        self._last_caption = None
        self._presenter.reset()
        self.lock_check.setChecked(False)
        self.history_view.clear()
        self._style_preview = False
        self.overlay.set_text("", "")
        self.overlay.set_wanted(True)
        self.visibility_button.setText("隐藏字幕")
        self.preview_button.setText("显隐悬浮字幕")
        for metric in self.metric_values.values():
            metric.setText("演示" if self.demo_check.isChecked() else "—")
        self._engine = Engine(self.settings, self.demo_check.isChecked())
        self._engine.event.connect(self._engine_event, Qt.ConnectionType.QueuedConnection)
        self.state_label.setText("●  正在启动")
        self.status_message.setText("正在准备会话…")
        self.start_button.setText("停止捕获")
        self.demo_check.setEnabled(False)
        self.preview_badge.setText("演示文本" if self._engine.demo else "等待音频")
        self._engine.start()

    def _stop_session(self, message: str) -> None:
        if not self._engine:
            return
        self.state_label.setText("●  正在停止")
        self.status_message.setText(message)
        self.start_button.setEnabled(False)
        self._clear_subtitles()
        self._engine.stop()

    def _engine_event(self, run_id: str, kind: str, payload) -> None:
        if not self._engine or run_id != self._engine.run_id:
            return
        if self._engine.stop_event.is_set() and kind not in {"stopped", "error"}:
            return
        if kind in {"status", "ready", "warning", "error"}:
            self.status_message.setText(str(payload))
        if kind == "ready":
            self.state_label.setText("●  演示运行中" if self._engine.demo else "●  捕获运行中")
        elif kind == "error":
            self._last_error = str(payload)
            self.state_label.setText("●  启动或处理失败")
        elif kind == "level":
            self.level_meter.setValue(min(100, round(float(payload) * 350)))
        elif kind == "clear":
            self._clear_subtitles()
        elif kind in {"caption", "translation"}:
            self._accept_caption(payload, kind == "translation")
        elif kind == "stopped":
            self._engine.deleteLater()
            self._engine = None
            self._clear_subtitles()
            self.start_button.setEnabled(True)
            self.start_button.setText("开始捕获")
            self.demo_check.setEnabled(True)
            self.preview_button.setText("预览悬浮字幕")
            self.level_meter.setValue(0)
            if self._restart:
                self._restart = False
                QTimer.singleShot(0, self.start_session)
            elif self._last_error:
                self.state_label.setText("●  会话失败")
                self.status_message.setText(self._last_error)
            else:
                self.state_label.setText("●  已停止")
                self.status_message.setText("会话已结束，系统音频采集已关闭。")

    def _accept_caption(self, caption: Caption, translation: bool) -> None:
        caption = replace(caption, original=simplified(caption.original, caption.language),
                          translation=simplified(caption.translation, self.settings.target))
        old = self._history.get(caption.utterance)
        if old and old.revision > caption.revision:
            return
        # Ignore translations that do not match the original's current revision.
        if translation and (not old or old.revision != caption.revision
                            or old.original != caption.original or old.language != caption.language):
            return
        self._history[caption.utterance] = caption
        while len(self._history) > 60:
            self._history.popitem(last=False)
        display = self._last_caption is None or caption.key >= self._last_caption.key
        # Idle hiding clears the presenter, but not the session's high-water
        # mark. A late translation may update history without reviving old text.
        if translation and self._last_caption is not None and self._presenter.current is None:
            display = False
        if self._last_caption is None or caption.key >= self._last_caption.key:
            self._last_caption = caption
        shown = self._presenter.push(caption, time.monotonic()) if display else None
        if shown:
            self._present_caption(shown)
        self._render_history()

    def _present_caption(self, caption: Caption) -> None:
        if not self._picker:
            self.overlay.set_text(caption.original, caption.translation)
        self.preview.original, self.preview.translation = caption.original, caption.translation
        self.preview.update()
        self.preview_badge.setText("演示文本" if self._engine and self._engine.demo else "实时字幕")
        if self._engine and not self._engine.demo:
            self.metric_values["asr"].setText(f"{caption.asr_ms:.0f} ms")
            self.metric_values["translation"].setText(f"{caption.translation_ms:.0f} ms" if caption.translation_ms is not None else "—")
            lag = max(0, (time.monotonic() - caption.speech_end_at) * 1000)
            self.metric_values["lag"].setText(f"{lag:.0f} ms")

    def _clear_subtitles(self) -> None:
        self._presenter.reset()
        self.overlay.set_text("", "")

    def _render_history(self) -> None:
        blocks = []
        for caption in self._history.values():
            source = html.escape(caption.original)
            target = html.escape(caption.translation)
            status = "" if caption.final else " <span style='color:#879CA8'>· 识别中</span>"
            blocks.append(f"<p style='margin:8px 0;color:#DCE8ED'>{source}{status}"
                          f"<br><span style='color:#FFFFFF'>{target or '…'}</span></p>")
        self.history_view.setHtml("".join(blocks))
        bar = self.history_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _tick(self) -> None:
        now = time.monotonic()
        if now - self._metrics_at >= 1:
            self._metrics_at = now
            cpu = self._process.cpu_percent() / (psutil.cpu_count() or 1)
            memory = self._process.memory_info().rss / 1024 ** 2
            self.cpu_label.setText(f"本应用 CPU {cpu:.1f}%  ·  内存 {memory:.0f} MB")
        if not self._style_preview and not self._picker:
            shown = self._presenter.advance(now)
            if shown:
                self._present_caption(shown)
            if self._presenter.expired(now):
                self._clear_subtitles()

    def _save(self) -> None:
        try:
            save_settings(self.config_path, self.settings)
        except (OSError, ValueError, TypeError) as error:
            self.status_message.setText(f"设置保存失败：{error}")

    def diagnose(self) -> None:
        lines = [f"平台：{platform.system()} {platform.release()} / Python {platform.python_version()}"]
        for field, names in (("streaming_model", ("encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt", "linguacaption.json")),
                             ("asr_model", ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")),
                             ("translation_model", ("model.bin", "config.json", "sentencepiece.bpe.model", "linguacaption.json"))):
            path = Path(getattr(self.settings, field)).expanduser().resolve()
            missing = [name for name in names if not (path / name).is_file()]
            lines.append(f"{field}：" + ("文件齐全（仍需实际加载验证）" if not missing else "缺少 " + ", ".join(missing)))
        if platform.system() == "Darwin":
            from .audio import macos_helper
            lines.append("macOS 原生采集程序：" + ("已构建" if macos_helper().is_file() else "请运行 bash scripts/build_macos.sh"))
        lines.append("500 ms / 95% 尚需使用真实音频及人工标注测试，详见 docs/ACCEPTANCE.md。")
        self.diagnostic.setText("\n".join(lines))

    def export_history(self) -> None:
        if not self._history:
            self.status_message.setText("当前没有可导出的会话文本。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出当前会话", "captions.txt", "Text (*.txt)")
        if path:
            text = "\n\n".join(c.original + ("\n" + c.translation if c.translation else "") for c in self._history.values())
            try:
                Path(path).write_text(text, encoding="utf-8")
            except OSError as error:
                QMessageBox.warning(self, "导出失败", str(error))

    def closeEvent(self, event) -> None:
        self._restart = False
        if self._engine:
            self._engine.stop()
        self.hotkeys.close()
        self.overlay.close()
        if self._picker:
            self._picker.blockSignals(True)
            self._picker.close()
        self._save_timer.stop()
        self._save()
        event.accept()
        self.closed.emit()
