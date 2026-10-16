import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qtapp():
    app = QApplication.instance() or QApplication([])
    if os.name == "nt":
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
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
    return app
