from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


def snap_value(
    value: int,
    minimum: int,
    maximum: int,
    default: int,
    divisions: int = 20,
) -> int:
    """Return the nearest scale mark, always treating the default as a mark."""
    if divisions <= 0:
        raise ValueError("divisions must be greater than zero")
    marks = {
        round(minimum + (maximum - minimum) * index / divisions)
        for index in range(divisions + 1)
    }
    marks.add(default)
    return min(marks, key=lambda mark: (abs(mark - value), abs(mark - default), mark))


class SnappingSlider(QSlider):
    """A scale slider that becomes continuous while Ctrl is held."""

    def __init__(
        self,
        minimum: int,
        maximum: int,
        value: int,
        default: int,
        divisions: int = 20,
    ) -> None:
        super().__init__(Qt.Orientation.Horizontal)
        self.default_value = default
        self.divisions = divisions
        self.setRange(minimum, maximum)
        self.setSingleStep(1)
        self.setPageStep(max(1, round((maximum - minimum) / divisions)))
        self.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.setTickInterval(self.pageStep())
        self.setValue(value)
        self.valueChanged.connect(self._show_value)
        self._show_value(value)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        self._snap_unless_ctrl(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        self._snap_unless_ctrl(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
        available = max(0, groove.width() - handle.width())
        offset = QStyle.sliderPositionFromValue(
            self.minimum(),
            self.maximum(),
            self.default_value,
            available,
            option.upsideDown,
        )
        x = groove.left() + handle.width() // 2 + offset
        painter = QPainter(self)
        painter.setPen(QPen(QColor("#F79009"), 2))
        painter.drawLine(x, groove.bottom() + 5, x, groove.bottom() + 17)

    def _snap_unless_ctrl(self, event: QMouseEvent) -> None:
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.setValue(
                snap_value(
                    self.value(),
                    self.minimum(),
                    self.maximum(),
                    self.default_value,
                    self.divisions,
                )
            )

    def _show_value(self, value: int) -> None:
        self.setToolTip(f"現在値: {value}（Ctrl+ドラッグで自由調整）")
