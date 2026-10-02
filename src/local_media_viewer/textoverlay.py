"""The text OCR read, drawn over the picture where it was found.

Each recognised line gets a pale box over its place on the page with the text
as read written inside it, so a misreading can be seen against its spot. The
box covers the original, which is why the overlay can be switched off.

Positions are in the pixels of the picture that was read. ImageView keeps this
item as a child of the picture and scales it along, so it follows zooming and
panning with no arithmetic of its own.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

# Nearly opaque: with the original showing through, the two texts tangle and
# neither can be read.
PAPER = QColor(255, 255, 255, 222)
OUTLINE = QColor("#2F6FDE")
INK = QColor("#0B2A66")
# A box this much taller than wide, holding more than one character, is a
# column of vertical writing.
VERTICAL_RATIO = 1.5
# How much of the box's thickness the letters fill.
FILL = 0.8


def is_vertical(text: str, box: QRectF) -> bool:
    return len(text) > 1 and box.height() > box.width() * VERTICAL_RATIO


class TextOverlay(QGraphicsItem):
    """`lines` are (text, quad) pairs; a quad is four (x, y) corners."""

    def __init__(self, parent: QGraphicsItem) -> None:
        super().__init__(parent)
        self.lines: list[tuple[str, QPolygonF]] = []
        self.bounds = QRectF()
        # Above the picture it belongs to, and never in the way of the mouse.
        self.setZValue(1)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def set_lines(self, lines: Sequence[tuple[str, Sequence[Sequence[float]]]]) -> None:
        self.prepareGeometryChange()
        self.lines = [
            (text, QPolygonF([QPointF(x, y) for x, y in quad])) for text, quad in lines if text
        ]
        bounds = QRectF()
        for _text, polygon in self.lines:
            bounds = bounds.united(polygon.boundingRect())
        # Room for the outline, which is drawn centred on the edge.
        self.bounds = bounds.adjusted(-2, -2, 2, 2) if self.lines else QRectF()
        self.update()

    def boundingRect(self) -> QRectF:
        return self.bounds

    def paint(
        self,
        painter: QPainter,
        _option: QStyleOptionGraphicsItem,
        _widget: QWidget | None = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        outline = QPen(OUTLINE, 1.5)
        # The same thickness on screen however far the picture is zoomed.
        outline.setCosmetic(True)
        for text, polygon in self.lines:
            painter.setPen(outline)
            painter.setBrush(PAPER)
            painter.drawPolygon(polygon)
            painter.setPen(INK)
            box = polygon.boundingRect()
            if is_vertical(text, box):
                self.draw_column(painter, text, box)
            else:
                self.draw_row(painter, text, box)

    def sized_font(self, painter: QPainter, pixels: float) -> QFont:
        font = QFont(painter.font())
        font.setPixelSize(max(1, round(pixels)))
        return font

    def draw_row(self, painter: QPainter, text: str, box: QRectF) -> None:
        font = self.sized_font(painter, box.height() * FILL)
        width = QFontMetricsF(font).horizontalAdvance(text)
        if width > box.width() and width > 0:
            # Shrunk to fit rather than clipped: every character read is shown.
            font = self.sized_font(painter, font.pixelSize() * box.width() / width)
        painter.setFont(font)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextDontClip, text)

    def draw_column(self, painter: QPainter, text: str, box: QRectF) -> None:
        """One character under another, top to bottom."""
        step = box.height() / len(text)
        painter.setFont(self.sized_font(painter, min(box.width(), step) * FILL))
        for index, character in enumerate(text):
            cell = QRectF(box.left(), box.top() + index * step, box.width(), step)
            painter.drawText(
                cell, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextDontClip, character
            )
