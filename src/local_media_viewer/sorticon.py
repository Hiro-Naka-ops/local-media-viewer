from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from local_media_viewer.media import SORT_CREATED, SORT_MODIFIED, SORT_NAME

# Drawn as SVG for the same reason the app icon is: it stays crisp at whatever
# size and scaling the status bar asks for, and the shapes stay readable in
# source. The box is 26 wide by 16 tall - a field mark on the left, the
# direction arrow on the right.
VIEW_WIDTH = 26.0
VIEW_HEIGHT = 16.0

# Bars of falling length: the ordinary "sorted" mark, used for name order.
NAME_GLYPH = (
    '<g fill="none" stroke="{color}" stroke-width="1.9" stroke-linecap="round">'
    '<path d="M2 3.6H13"/><path d="M2 8H9.4"/><path d="M2 12.4H5.8"/>'
    "</g>"
)

# A calendar with a plus on it: the day the file came into being.
CREATED_GLYPH = (
    '<g fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<rect x="1.6" y="3.4" width="12.8" height="11.2" rx="1.6"/>'
    '<path d="M1.6 7H14.4"/>'
    '<path d="M4.9 1.6V4.4"/><path d="M11.1 1.6V4.4"/>'
    '<path d="M8 9.2V12.6"/><path d="M6.3 10.9H9.7"/>'
    "</g>"
)

# A clock: the time the file was last changed. A pencil would say "edited"
# more directly, but at the size the status bar shows this it collapses into a
# plain diagonal stroke, whereas the circle stays legible and cannot be
# mistaken for the calendar's square.
MODIFIED_GLYPH = (
    '<g fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<circle cx="8" cy="8.6" r="5.9"/><path d="M8 4.9V8.6H11.1"/>'
    "</g>"
)

GLYPHS = {
    SORT_NAME: NAME_GLYPH,
    SORT_CREATED: CREATED_GLYPH,
    SORT_MODIFIED: MODIFIED_GLYPH,
}

# Up for ascending, down for descending, matching the carets Explorer puts in
# its column headers.
ASCENDING_ARROW = "M21 1.8 25 7.2H22.3V14.2H19.7V7.2H17Z"
DESCENDING_ARROW = "M21 14.2 25 8.8H22.3V1.8H19.7V8.8H17Z"

ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 26 16" '
    'width="26" height="16">{glyph}<path d="{arrow}" fill="{color}"/></svg>'
)

_cache: dict[tuple[str, bool, int, str, int], QPixmap] = {}


def sort_icon_svg(key: str, descending: bool, color: str) -> str:
    glyph = GLYPHS.get(key, NAME_GLYPH).format(color=color)
    arrow = DESCENDING_ARROW if descending else ASCENDING_ARROW
    return ICON_SVG.format(glyph=glyph, arrow=arrow, color=color)


def sort_icon(key: str, descending: bool, height: int, color: str, ratio: float = 1.0) -> QPixmap:
    """A small mark showing which field the files are ordered by, and which way."""
    # Rounded into the cache key so a fractional screen scaling does not make
    # every repaint a cache miss.
    steps = max(1, round(ratio * 4))
    cached = _cache.get((key, descending, height, color, steps))
    if cached is not None:
        return cached
    scale = steps / 4
    width = round(height * VIEW_WIDTH / VIEW_HEIGHT)
    image = QImage(round(width * scale), round(height * scale), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(sort_icon_svg(key, descending, color).encode("utf-8")).render(
        painter, QRectF(0, 0, image.width(), image.height())
    )
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(scale)
    _cache[(key, descending, height, color, steps)] = pixmap
    return pixmap
