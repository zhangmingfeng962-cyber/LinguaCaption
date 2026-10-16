from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from .config import load_settings
from .ui import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="LinguaCaption 本地双语字幕")
    parser.add_argument("--demo", action="store_true", help="Start a labeled demonstration, without audio capture")
    parser.add_argument("--config", type=Path, help="Settings JSON (default: ./local/settings.json)")
    args = parser.parse_args()
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    config_path = args.config or base / "local/settings.json"
    app = QApplication(sys.argv[:1])
    app.setApplicationName("LinguaCaption")
    app.setOrganizationName("LinguaCaption")
    app.setQuitOnLastWindowClosed(False)
    font = QFont("Microsoft YaHei UI" if sys.platform == "win32" else "PingFang SC")
    font.setPixelSize(13)
    app.setFont(font)
    try:
        settings = load_settings(config_path)
    except (OSError, ValueError, TypeError) as error:
        QMessageBox.critical(None, "设置读取失败", f"{config_path}\n{error}\n请修正此文件或使用 --config 指定新文件。")
        return 1
    window = MainWindow(settings, config_path, demo=args.demo)
    window.show()
    # Close is an explicit exit; a frameless overlay must not keep the app alive.
    window.closed.connect(app.quit)
    if args.demo:
        QTimer.singleShot(200, window.start_session)
    return app.exec()
