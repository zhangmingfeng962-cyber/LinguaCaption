from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def make_icons() -> Path:
    application = QApplication.instance() or QApplication([])
    assets = Path(__file__).resolve().parents[1] / "src/linguacaption/assets"
    renderer = QSvgRenderer(str(assets / "app.svg"))
    image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    image.save(str(assets / "app.png"))
    with Image.open(assets / "app.png") as source:
        source.save(assets / "app.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        if sys.platform == "darwin":
            iconset = assets / "app.iconset"
            iconset.mkdir(exist_ok=True)
            for size in (16, 32, 128, 256, 512):
                for factor in (1, 2):
                    suffix = "@2x" if factor == 2 else ""
                    source.resize((size * factor, size * factor), Image.Resampling.LANCZOS).save(
                        iconset / f"icon_{size}x{size}{suffix}.png")
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(assets / "app.icns")], check=True)
    _ = application
    return assets


if __name__ == "__main__":
    print(make_icons())
