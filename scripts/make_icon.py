"""Generate the app icon: assets/icon.svg, the PNG sizes and icon.ico.

The M is one continuous stroke, so its centre is a real pointed join rather
than two separate strokes whose round ends only just overlapped (which read as
a pinched, half-connected joint, most visibly at the Mac's 1024 px). The
two-tone look is kept by cutting that one outline down the middle.

The cut is done here, into plain filled shapes, because Qt's SVG renderer
ignores <clipPath>; filled paths draw the same in every renderer.

Usage (from the repo root):  python scripts/make_icon.py
It also rewrites ICON_SVG in src/local_media_viewer/appicon.py, the copy the
app draws its window icon from, so the two never drift apart.
"""

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QTransform,
)
from PySide6.QtSvg import QSvgRenderer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mikan  # noqa: E402  (a sibling script, not an installed package)

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)

BACKGROUND = "#F0880D"
STROKE_WIDTH = 27.0
# Centre line of the M, in the same units the old icon used: 156 wide, 116
# tall, the two arms meeting at the middle, (78, 80).
CENTRE_LINE = [(0.0, 116.0), (0.0, 0.0), (78.0, 80.0), (156.0, 0.0), (156.0, 116.0)]
# Placed in the 256 box at the size it always had, upright. Leaning it left
# (5 to 12 degrees) and shifting it left were both tried and dropped.
M_SCALE = 0.80874
M_TILT = 0
PLACEMENT = f"translate(128 128) rotate({M_TILT}) scale({M_SCALE}) translate(-78.000 -58.000)"
RIGHT_OPACITY = 0.62

# The mikan (みかん, an M fruit) on the M's right leg. Its shape lives in
# scripts/mikan.py, shared with the standalone files in assets/mikan/.
MIKAN_COLOUR = mikan.YELLOW
MIKAN_SCALE = 1.85
# Tilted to the right, turning about the body's centre (degrees clockwise).
MIKAN_ROTATION = 20
# How far right of the M's right foot the fruit's centre sits.
MIKAN_OFFSET = 8
# An amber ring round the fruit cuts it out of the white M it overlaps, so the
# two silhouettes stay apart instead of merging into one blob.
KEYLINE = 7


def outline() -> QPainterPath:
    line = QPainterPath(QPointF(*CENTRE_LINE[0]))
    for point in CENTRE_LINE[1:]:
        line.lineTo(QPointF(*point))
    stroker = QPainterPathStroker()
    stroker.setWidth(STROKE_WIDTH)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    # Curves are flattened by the cut below; a fine curve threshold keeps the
    # round ends round even at 1024 px.
    stroker.setCurveThreshold(0.05)
    return stroker.createStroke(line).simplified()


def m_transform() -> QTransform:
    """PLACEMENT as a QTransform, to measure the M where it is drawn."""
    return QTransform().translate(128, 128).rotate(M_TILT).scale(M_SCALE, M_SCALE).translate(-78, -58)


# Where the tilted M lands in the tile, measured from its drawn outline.
M_BOX = m_transform().map(outline()).boundingRect()
M_BOTTOM = M_BOX.bottom()
M_LEFT = M_BOX.left()
M_RIGHT_FOOT = m_transform().map(QPointF(*CENTRE_LINE[-1]))
# The fruit's bottom stands on the M's lowest point (asked for by the user).
# Both are measured from the drawn shapes, so a change of angle or shape
# keeps them on one line.
MIKAN_X = M_RIGHT_FOOT.x() + MIKAN_OFFSET
MIKAN_Y = M_BOTTOM - mikan.body_bottom(MIKAN_ROTATION) * MIKAN_SCALE
# The fruit sticks out to the right of the M, so the pair is shifted left to
# sit centred in the tile as one mark.
MARK_RIGHT = MIKAN_X + mikan.outline(MIKAN_ROTATION).boundingRect().right() * MIKAN_SCALE
SHIFT_X = 128 - (M_LEFT + MARK_RIGHT) / 2


def svg_path(path: QPainterPath) -> str:
    parts = []
    for index in range(path.elementCount()):
        element = path.elementAt(index)
        command = "M" if element.isMoveTo() else "L"
        parts.append(f"{command}{element.x:.2f} {element.y:.2f}")
    return " ".join(parts) + " Z"


def icon_svg() -> str:
    whole = outline()
    middle = CENTRE_LINE[2][0]
    margin = STROKE_WIDTH
    left_box = QPainterPath()
    left_box.addRect(QRectF(-margin, -margin, middle + margin, 116 + 2 * margin))
    right_box = QPainterPath()
    right_box.addRect(QRectF(middle, -margin, 156 - middle + margin, 116 + 2 * margin))
    left = whole.intersected(left_box)
    right = whole.intersected(right_box)
    cx, cy = mikan.BODY_CENTRE
    fruit = (
        f'transform="translate({MIKAN_X:.2f} {MIKAN_Y:.2f}) scale({MIKAN_SCALE}) '
        f'rotate({MIKAN_ROTATION} {cx:g} {cy:g})"'
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">'
        f'<rect width="256" height="256" rx="58" fill="{BACKGROUND}"/>'
        f'<g transform="translate({SHIFT_X:.2f} 0)">'
        f'<g transform="{PLACEMENT}">'
        f'<path d="{svg_path(left)}" fill="#FFFFFF"/>'
        f'<path d="{svg_path(right)}" fill="#FFFFFF" fill-opacity="{RIGHT_OPACITY}"/>'
        "</g>"
        # The keyline first: the silhouette in the background colour, widened
        # by a stroke, then the fruit on top of it.
        f'<g {fruit} fill="{BACKGROUND}" stroke="{BACKGROUND}" '
        f'stroke-width="{KEYLINE / MIKAN_SCALE:.2f}" stroke-linejoin="round">'
        f"{mikan.shapes()}</g>"
        f'<g {fruit} fill="{MIKAN_COLOUR}">{mikan.shapes()}</g>'
        "</g></svg>"
    )


def render(svg: str, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(svg.encode("utf-8")).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def main() -> None:
    QGuiApplication(sys.argv[:1])
    svg = icon_svg()
    if "--preview" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--preview") + 1])
        render(svg, 1024).save(str(out))
        return
    (ASSETS / "icon.svg").write_bytes(svg.encode("utf-8"))
    for size in SIZES:
        render(svg, size).save(str(ASSETS / f"icon-{size}.png"))
    images = [Image.open(ASSETS / f"icon-{size}.png") for size in SIZES]
    images[-1].save(ASSETS / "icon.ico", sizes=[(size, size) for size in SIZES], append_images=images)
    embed(svg)


def embed(svg: str) -> None:
    """Put the SVG into appicon.py, where the running app reads it from.

    Split with backslash-newline continuations inside the string, which Python
    drops, so the lines stay under ruff's 100 columns and the text is unchanged.
    """
    continuation = "\\" + "\n"
    chunks = [svg[i : i + 88] for i in range(0, len(svg), 88)]
    block = 'ICON_SVG = """' + continuation + continuation.join(chunks) + '"""'
    path = ROOT / "src" / "local_media_viewer" / "appicon.py"
    source = path.read_text(encoding="utf-8")
    start = source.index('ICON_SVG = """')
    end = source.index('"""', start + len('ICON_SVG = """')) + 3
    # newline="" keeps LF line endings on Windows (see .claude/CLAUDE.md).
    with open(path, "w", encoding="utf-8", newline="") as file:
        file.write(source[:start] + block + source[end:])


if __name__ == "__main__":
    main()
