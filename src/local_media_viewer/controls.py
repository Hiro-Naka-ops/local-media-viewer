from __future__ import annotations

from PySide6.QtCore import QLineF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSlider, QStyle, QStyleOptionSlider

from local_media_viewer.i18n import tr


class ClickableLabel(QLabel):
    """A label that reports a left click, and shows a hand to say it can."""

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        # On release and only inside, like a button: pressing and then sliding
        # off is how a click is taken back.
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


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

    def marks(self) -> list[int]:
        """The values the slider snaps to, in order: the regular marks."""
        span = self.maximum() - self.minimum()
        return [
            round(self.minimum() + span * index / self.divisions)
            for index in range(self.divisions + 1)
        ]

    def handle_centre(self, option: QStyleOptionSlider, value: int) -> float:
        """Where the style centres the handle for a value, in widget pixels."""
        option.sliderPosition = value
        option.sliderValue = value
        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self
        )
        return rect.left() + rect.width() / 2

    def value_x(self, option: QStyleOptionSlider, value: int) -> float:
        """The x a value sits at, spaced evenly between the two ends.

        Asked of the style at the two ends only and interpolated between, so the
        marks are evenly spaced whatever the platform. The macOS style lays the
        handle out differently from Windows, and the old sum of Windows-style
        metrics put the marks and the default line in the wrong places there.
        """
        start = self.handle_centre(option, self.minimum())
        end = self.handle_centre(option, self.maximum())
        span = self.maximum() - self.minimum()
        return start + (end - start) * (value - self.minimum()) / span if span else start

    def paintEvent(self, event: QPaintEvent) -> None:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        painter = QPainter(self)
        # The style is asked for the groove and handle only; the tick marks are
        # drawn below instead. Native marks come out unevenly spaced on macOS,
        # and never lined up with the default line drawn on top of them.
        # tickPosition stays TicksBelow so the layout still leaves them room.
        option.subControls = (
            QStyle.SubControl.SC_SliderGroove | QStyle.SubControl.SC_SliderHandle
        )
        self.style().drawComplexControl(QStyle.ComplexControl.CC_Slider, option, painter, self)

        geometry = QStyleOptionSlider()
        self.initStyleOption(geometry)
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, geometry, QStyle.SubControl.SC_SliderHandle, self
        )
        top = min(handle.bottom() + 3, self.height() - 5)
        bottom = min(top + 4, self.height() - 1)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ticks = QColor(self.palette().color(self.foregroundRole()))
        ticks.setAlpha(110)
        painter.setPen(QPen(ticks, 1))
        for mark in self.marks():
            x = self.value_x(geometry, mark)
            painter.drawLine(QLineF(x, top, x, bottom))
        # The default gets a longer orange mark of its own, on the same scale.
        x = self.value_x(geometry, self.default_value)
        painter.setPen(QPen(QColor("#F79009"), 2))
        painter.drawLine(QLineF(x, top - 2, x, min(bottom + 5, self.height() - 1)))
        painter.end()

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

    def retranslate(self) -> None:
        self._show_value(self.value())

    def _show_value(self, value: int) -> None:
        self.setToolTip(tr("現在値: {value}（Ctrl+ドラッグで自由調整）", value=value))
