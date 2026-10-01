"""Page-change animations for the slideshow.

A transition never touches how a page is drawn. The view is photographed
before and after the page changes, and a widget laid over it animates from one
photograph to the other, then gets out of the way. Paging by hand skips all of
this, so it stays as fast as it was.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QWidget

NONE = "none"
FADE = "fade"
FADE_BLACK = "fade_black"
SLIDE_LEFT = "slide_left"
SLIDE_UP = "slide_up"
ZOOM = "zoom"

TRANSITION_LABELS = [
    (NONE, "なし"),
    (FADE, "フェード"),
    (FADE_BLACK, "フェードアウト → フェードイン"),
    (SLIDE_LEFT, "スライドイン（右から）"),
    (SLIDE_UP, "スライドイン（下から）"),
    (ZOOM, "ズームイン"),
]
TRANSITIONS = {key for key, _label in TRANSITION_LABELS}

# How long one change takes, in milliseconds.
SPEED_LABELS = [(300, "速い"), (600, "標準"), (1200, "ゆっくり")]
SPEEDS = {duration for duration, _label in SPEED_LABELS}

# The old page grows to this much of its size as it fades away in the zoom.
# Growing the old one rather than the new keeps the whole view covered: a new
# page starting small left the old one showing as a frame round it.
ZOOM_END = 1.15


def paint_transition(
    painter: QPainter,
    kind: str,
    progress: float,
    before: QPixmap,
    after: QPixmap,
    width: float,
    height: float,
) -> None:
    """Draw one moment of the change: progress 0 is the old page, 1 the new."""
    # Rectangles rather than positions: a grabbed pixmap is in device pixels,
    # and drawing it into a logical rectangle is what keeps it the right size
    # on a scaled display.
    full = QRectF(0, 0, width, height)

    def draw(pixmap: QPixmap, target: QRectF, opacity: float = 1.0) -> None:
        painter.setOpacity(opacity)
        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))

    # The view's own background, for the frames where neither page covers it.
    painter.fillRect(full, Qt.GlobalColor.black)
    if kind == FADE_BLACK:
        if progress < 0.5:
            draw(before, full, 1.0 - progress * 2)
        else:
            draw(after, full, progress * 2 - 1.0)
    elif kind == SLIDE_LEFT:
        draw(before, full.translated(-progress * width, 0))
        draw(after, full.translated(width - progress * width, 0))
    elif kind == SLIDE_UP:
        draw(before, full.translated(0, -progress * height))
        draw(after, full.translated(0, height - progress * height))
    elif kind == ZOOM:
        scale = 1.0 + (ZOOM_END - 1.0) * progress
        grown = QRectF(0, 0, width * scale, height * scale)
        grown.moveCenter(full.center())
        draw(after, full)
        draw(before, grown, 1.0 - progress)
    else:
        draw(before, full)
        draw(after, full, progress)
    painter.setOpacity(1.0)


class TransitionOverlay(QWidget):
    """Covers a widget for the length of one page change."""

    def __init__(self, target: QWidget) -> None:
        super().__init__(target)
        self.target = target
        self.kind = FADE
        self.progress = 1.0
        self.before = QPixmap()
        self.after = QPixmap()
        # Clicks, the wheel and the right-click menu still reach the view.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.valueChanged.connect(self.set_progress)
        self.animation.finished.connect(self.cancel)
        target.installEventFilter(self)
        self.hide()

    def running(self) -> bool:
        return self.isVisibleTo(self.target)

    def play(self, kind: str, duration: int, before: QPixmap, after: QPixmap) -> None:
        self.cancel()
        if kind not in TRANSITIONS or kind == NONE or before.isNull() or after.isNull():
            return
        self.kind = kind
        self.before = before
        self.after = after
        self.progress = 0.0
        self.setGeometry(self.target.rect())
        self.raise_()
        self.show()
        self.animation.setDuration(duration)
        self.animation.start()

    def cancel(self) -> None:
        """Drop straight to the page underneath, which is already the new one."""
        self.animation.stop()
        self.hide()
        self.before = QPixmap()
        self.after = QPixmap()

    def set_progress(self, value: float) -> None:
        self.progress = float(value)
        self.update()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # The photographs are of the old size; stretching them over a resized
        # view would smear the picture, so the change just ends.
        if watched is self.target and event.type() == QEvent.Type.Resize and self.running():
            self.cancel()
        return False

    def paintEvent(self, _event: QPaintEvent) -> None:
        if self.before.isNull() or self.after.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        paint_transition(
            painter, self.kind, self.progress, self.before, self.after, self.width(), self.height()
        )
        painter.end()
