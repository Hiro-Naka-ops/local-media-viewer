from __future__ import annotations

import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Copied from assets/icon.svg. Kept in the source rather than read from disk so
# the window icon is present no matter how the app is started: from the repo,
# from an installed wheel, or from the one-file EXE, which unpacks to a
# temporary directory and carries no assets folder.
ICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256"><\
rect width="256" height="256" rx="58" fill="#F0880D"/><g transform="translate(-15.27 0)"\
><g transform="translate(128 128) scale(0.80874) translate(-78.000 -58.000)"><path d="M-\
13.50 116.00 L-13.50 0.00 L-13.39 -1.69 L-13.09 -3.32 L-12.59 -4.88 L-11.92 -6.35 L-11.0\
8 -7.71 L-10.09 -8.97 L-8.97 -10.09 L-7.71 -11.08 L-6.35 -11.92 L-4.88 -12.59 L-3.32 -13\
.09 L-1.69 -13.39 L0.00 -13.50 L1.69 -13.39 L3.32 -13.09 L4.88 -12.59 L6.35 -11.92 L7.71\
 -11.08 L8.97 -10.09 L9.67 -9.39 L9.67 -9.42 L78.00 60.66 L78.00 93.50 L76.75 93.44 L75.\
53 93.28 L74.35 93.00 L73.22 92.63 L72.13 92.16 L71.09 91.60 L70.11 90.95 L69.19 90.23 L\
68.33 89.42 L68.33 89.42 L13.50 33.18 L13.50 116.00 L13.39 117.69 L13.09 119.32 L12.59 1\
20.88 L11.92 122.35 L11.08 123.71 L10.09 124.97 L8.97 126.09 L7.71 127.08 L6.35 127.92 L\
4.88 128.59 L3.32 129.09 L1.69 129.39 L0.00 129.50 L-1.69 129.39 L-3.32 129.09 L-4.88 12\
8.59 L-6.35 127.92 L-7.71 127.08 L-8.97 126.09 L-10.09 124.97 L-11.08 123.71 L-11.92 122\
.35 L-12.59 120.88 L-13.09 119.32 L-13.39 117.69 L-13.50 116.00 Z" fill="#FFFFFF"/><path\
 d="M78.00 60.66 L146.33 -9.42 L147.19 -10.23 L148.11 -10.95 L149.09 -11.60 L150.13 -12.\
16 L151.22 -12.63 L152.35 -13.00 L153.53 -13.28 L154.75 -13.44 L156.00 -13.50 L157.69 -1\
3.39 L159.32 -13.09 L160.88 -12.59 L162.35 -11.92 L163.71 -11.08 L164.97 -10.09 L166.09 \
-8.97 L167.08 -7.71 L167.92 -6.35 L168.59 -4.88 L169.09 -3.32 L169.39 -1.69 L169.50 0.00\
 L169.50 116.00 L169.39 117.69 L169.09 119.32 L168.59 120.88 L167.92 122.35 L167.08 123.\
71 L166.09 124.97 L164.97 126.09 L163.71 127.08 L162.35 127.92 L160.88 128.59 L159.32 12\
9.09 L157.69 129.39 L156.00 129.50 L154.31 129.39 L152.68 129.09 L151.12 128.59 L149.65 \
127.92 L148.29 127.08 L147.03 126.09 L145.91 124.97 L144.92 123.71 L144.08 122.35 L143.4\
1 120.88 L142.91 119.32 L142.61 117.69 L142.50 116.00 L142.50 33.18 L87.67 89.42 L86.81 \
90.23 L85.89 90.95 L84.91 91.60 L83.87 92.16 L82.78 92.63 L81.65 93.00 L80.47 93.28 L79.\
25 93.44 L78.00 93.50 Z" fill="#FFFFFF" fill-opacity="0.62"/></g><g transform="translate\
(201.08 146.97) scale(1.85)" fill="#F0880D" stroke="#F0880D" stroke-width="3.78" stroke-\
linejoin="round"><circle cx="0" cy="4" r="17"/><circle cx="0" cy="-13" r="2.6"/><ellipse\
 cx="8.5" cy="-19" rx="8.5" ry="4.2" transform="rotate(-28 8.5 -19)"/></g><g transform="\
translate(201.08 146.97) scale(1.85)" fill="#FFFFFF"><circle cx="0" cy="4" r="17"/><circ\
le cx="0" cy="-13" r="2.6"/><ellipse cx="8.5" cy="-19" rx="8.5" ry="4.2" transform="rota\
te(-28 8.5 -19)"/></g></g></svg>"""

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
    # Imported here: ctypes.windll exists only on Windows.
    from ctypes import windll

    try:
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_MODEL_ID)
    except (AttributeError, OSError):
        pass
