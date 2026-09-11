from __future__ import annotations

import sys
from ctypes import windll

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Copied from assets/icon.svg. Kept in the source rather than read from disk so
# the window icon is present no matter how the app is started: from the repo,
# from an installed wheel, or from the one-file EXE, which unpacks to a
# temporary directory and carries no assets folder.
ICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">\
<rect width="256" height="256" rx="58" fill="#F0880D"/>\
<g transform="translate(128 128) scale(0.80874) translate(-78.000 -58.000)">\
<path d="M 0.0 116.0 L 0.0 0.0 L 65.43419754966828 67.11199748683927" fill="none" \
stroke="#FFFFFF" stroke-width="27.0" stroke-opacity="1.0" stroke-linejoin="round" \
stroke-linecap="round"/>\
<path d="M 90.56580245033172 67.11199748683927 L 156.0 0.0 L 156.0 116.0" fill="none" \
stroke="#FFFFFF" stroke-width="27.0" stroke-opacity="0.62" stroke-linejoin="round" \
stroke-linecap="round"/></g></svg>"""

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
APP_MODEL_ID = "LocalMediaViewer.Viewer"

_icon: QIcon | None = None


def app_icon() -> QIcon:
    """The window and taskbar icon, rasterised once per run."""
    global _icon
    if _icon is not None:
        return _icon
    renderer = QSvgRenderer(ICON_SVG.encode("utf-8"))
    icon = QIcon()
    for size in ICON_SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        icon.addPixmap(QPixmap.fromImage(image))
    _icon = icon
    return _icon


def claim_taskbar_identity() -> None:
    """Let Windows group the window under our own icon.

    Without an explicit model id a script launched through python.exe inherits
    the interpreter's taskbar icon, whatever the window icon says.
    """
    if sys.platform != "win32":
        return
    try:
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_MODEL_ID)
    except (AttributeError, OSError):
        pass
