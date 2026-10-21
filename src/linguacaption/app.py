from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .config import load_settings
from .runtime import configure_model_paths, default_config_path
from .ui import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="LinguaCaption 本地双语字幕")
    parser.add_argument("--demo", action="store_true", help="Start a labeled demonstration, without audio capture")
    parser.add_argument("--config", type=Path, help="Optional settings JSON; default is the writable user config directory")
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test-report", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--self-test-audio", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("LinguaCaption")
    app.setOrganizationName("LinguaCaption")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets/app.png")))
    app.setQuitOnLastWindowClosed(False)
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPixelSize(13)
    app.setFont(font)
    try:
        config_path = args.config or default_config_path()
        settings = configure_model_paths(load_settings(config_path))
    except (OSError, ValueError, TypeError) as error:
        QMessageBox.critical(None, "设置读取失败", f"{error}\n请修正设置文件或使用 --config 指定新文件。")
        return 1
    if args.self_test:
        if args.self_test_report is None:
            parser.error("--self-test requires --self-test-report")
        from .diagnostics import run_packaged_test
        return run_packaged_test(app, settings, config_path, args.self_test_report, args.self_test_audio)
    window = MainWindow(settings, config_path, demo=args.demo)
    window.show()
    # Close is an explicit exit; a frameless overlay must not keep the app alive.
    window.closed.connect(app.quit)
    if args.demo:
        QTimer.singleShot(200, window.start_session)
    return app.exec()
