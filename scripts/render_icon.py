"""Write the app icon as a large PNG for the macOS bundle.

PyInstaller turns a PNG into the .icns a Mac app needs, but the Retina Dock
wants 1024 px, larger than any PNG kept in assets/, so the icon is drawn from
the same SVG the window uses. Usage: python scripts/render_icon.py OUT.png
"""

import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from local_media_viewer.appicon import ICON_SVG

SIZE = 1024

app = QGuiApplication(sys.argv[:1])
image = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
QSvgRenderer(ICON_SVG.encode("utf-8")).render(painter, QRectF(0, 0, SIZE, SIZE))
painter.end()
if not image.save(sys.argv[1]):
    raise SystemExit(f"could not write {sys.argv[1]}")
