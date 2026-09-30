"""The mikan (みかん) mark: one definition for the app icon and for reuse.

As plain as the Apple apple: a round body, a small stem and a separate leaf.
(A version with a star calyx, a squat body and a leaf vein was tried and
dropped: the simple one reads better.)

Run it to write the reusable files into assets/mikan/:
    python scripts/mikan.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPainterPath, QTransform
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "mikan"

YELLOW = "#FFE600"

# In the mark's own units: the body is a circle of radius 17 centred 4 below
# the origin, the stem a small dot on top, the leaf an ellipse tilted up and
# away to the right.
BODY_CENTRE = (0.0, 4.0)
BODY_RADIUS = 17.0
STEM_CENTRE = (0.0, -13.0)
STEM_RADIUS = 2.6
LEAF_CENTRE = (8.5, -19.0)
LEAF_RADII = (8.5, 4.2)
LEAF_ANGLE = -28.0


def shapes() -> str:
    """The mark's SVG elements, unfilled, for a <g fill=...> to colour."""
    (bx, by), (sx, sy), (lx, ly) = BODY_CENTRE, STEM_CENTRE, LEAF_CENTRE
    rx, ry = LEAF_RADII
    return (
        f'<circle cx="{bx:g}" cy="{by:g}" r="{BODY_RADIUS:g}"/>'
        f'<circle cx="{sx:g}" cy="{sy:g}" r="{STEM_RADIUS:g}"/>'
        f'<ellipse cx="{lx:g}" cy="{ly:g}" rx="{rx:g}" ry="{ry:g}" '
        f'transform="rotate({LEAF_ANGLE:g} {lx:g} {ly:g})"/>'
    )


def outline(rotation: float = 0.0) -> QPainterPath:
    """The mark's silhouette turned clockwise by `rotation` degrees about the
    body's centre, the same turn the icon gives it, for measuring its extent."""
    path = QPainterPath()
    path.addEllipse(QPointF(*BODY_CENTRE), BODY_RADIUS, BODY_RADIUS)
    stem = QPainterPath()
    stem.addEllipse(QPointF(*STEM_CENTRE), STEM_RADIUS, STEM_RADIUS)
    leaf = QPainterPath()
    leaf.addEllipse(QPointF(0, 0), *LEAF_RADII)
    leaf = QTransform().translate(*LEAF_CENTRE).rotate(LEAF_ANGLE).map(leaf)
    path = path.united(stem).united(leaf)
    cx, cy = BODY_CENTRE
    return QTransform().translate(cx, cy).rotate(rotation).translate(-cx, -cy).map(path)


def body_bottom(rotation: float = 0.0) -> float:
    """The lowest point of the body. A circle turned about its own centre does
    not move, but measuring keeps this true if the body is ever reshaped."""
    body = QPainterPath()
    body.addEllipse(QPointF(*BODY_CENTRE), BODY_RADIUS, BODY_RADIUS)
    cx, cy = BODY_CENTRE
    turn = QTransform().translate(cx, cy).rotate(rotation).translate(-cx, -cy)
    return turn.map(body).boundingRect().bottom()


def standalone_svg(colour: str = YELLOW, padding: float = 2.0) -> str:
    """The mark on its own, its viewBox fitted to the shape."""
    box = outline().boundingRect().adjusted(-padding, -padding, padding, padding)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{box.x():.2f} {box.y():.2f} {box.width():.2f} {box.height():.2f}">'
        f'<g fill="{colour}">{shapes()}</g></svg>'
    )


def render(svg: str, width: int) -> QImage:
    renderer = QSvgRenderer(svg.encode("utf-8"))
    size = renderer.defaultSize()
    height = round(width * size.height() / size.width())
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    return image


def main() -> None:
    QGuiApplication(sys.argv[:1])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mikan.svg").write_bytes(standalone_svg(YELLOW).encode("utf-8"))
    # currentColor takes the colour of the surrounding text in HTML/CSS.
    (OUT / "mikan-mono.svg").write_bytes(standalone_svg("currentColor").encode("utf-8"))
    for width in (64, 128, 256, 512, 1024):
        render(standalone_svg(YELLOW), width).save(str(OUT / f"mikan-{width}.png"))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
