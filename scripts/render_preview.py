"""Render our own Qt widgets to PNG without capturing the user's screen."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from linguacaption.config import Settings  # noqa: E402
from linguacaption.overlay import SubtitleOverlay  # noqa: E402
from linguacaption.ui import MainWindow  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--config", type=Path, required=True, help="Scratch path for this render")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    # The Windows offscreen QPA plugin does not enumerate system fonts.
    if os.name == "nt":
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    else:
        for path in ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
                     "/System/Library/Fonts/Supplemental/Arial.ttf"):
            if Path(path).is_file():
                QFontDatabase.addApplicationFont(path)
    families = QFontDatabase.families()
    family = next((name for name in ("Microsoft YaHei UI", "PingFang SC", "Heiti SC", "Arial") if name in families),
                  "sans-serif")
    font = QFont(family)
    font.setPixelSize(13)
    app.setFont(font)
    settings = Settings(font_family=font.family())
    window = MainWindow(settings, args.config, demo=True, register_hotkeys=False)
    window.resize(1280, 1024)
    window.show()
    app.processEvents()
    for page, filename in ((0, "workbench.png"), (1, "appearance.png"), (2, "models.png")):
        window.navigate(page)
        app.processEvents()
        if not window.grab().save(str(args.output / filename)):
            raise RuntimeError("PNG export failed")
        if page == 1:
            scrollbar = window.pages.widget(1).verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            app.processEvents()
            window.grab().save(str(args.output / "positions.png"))
    overlay = SubtitleOverlay(settings)
    overlay.set_text("The world is closer when we understand each other.", "听见世界，也读懂世界。")
    app.processEvents()
    overlay.grab().save(str(args.output / "overlay.png"))
    overlay.close()
    window.close()
    print(f"Rendered: {args.output.resolve()}")


if __name__ == "__main__":
    main()
