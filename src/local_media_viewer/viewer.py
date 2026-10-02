from __future__ import annotations

from collections import OrderedDict
from math import sqrt

from PySide6.QtCore import (
    QEvent,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QContextMenuEvent,
    QCursor,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from local_media_viewer.textoverlay import TextOverlay

# Drivers commonly map a tilt wheel onto the back/forward side buttons, so
# those turn pages too.
PAGE_BUTTONS = {
    Qt.MouseButton.BackButton: -1,
    Qt.MouseButton.ForwardButton: 1,
}


# How a picture is fitted to the view. The keys are stored in the settings.
FIT_WINDOW = "window"
FIT_WIDTH = "width"
FIT_HEIGHT = "height"
# Fixed-width fits: the picture's width is pinned to this percentage of the
# view, centred, leaving equal margins on both sides (100% at the narrowest
# still overflowing side is the same picture as FIT_WIDTH, just centred
# instead of pinned left). 60% is roughly the 1:3:1 margin-image-margin split.
NARROW_PERCENTS = (100, 80, 60, 40, 20)


def narrow_kind(percent: int) -> str:
    return f"narrow{percent}"


def narrow_percent(kind: str) -> int | None:
    """The percentage a narrow fit kind encodes, or None for any other kind."""
    if kind.startswith("narrow") and kind[len("narrow") :].isdigit():
        return int(kind[len("narrow") :])
    return None


FIT_NARROW_KINDS = tuple(narrow_kind(percent) for percent in NARROW_PERCENTS)
FIT_KINDS = (FIT_WINDOW, FIT_WIDTH, FIT_HEIGHT) + FIT_NARROW_KINDS
# The fitted side is pinned to its start rather than centred. When the fit
# overflows the other side, QGraphicsView centres using a scroll bar width that
# differs from the one the Windows 11 style draws, which left the picture a few
# pixels off the edge; pinned, it lands exactly. The other side still centres.
FIT_ALIGNMENT = {
    FIT_WINDOW: Qt.AlignmentFlag.AlignCenter,
    FIT_WIDTH: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    FIT_HEIGHT: Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
    # Pinned left too, and centred by hand in centre_narrow_fit for the same
    # reason: Qt's own centring sits half a bar off once the bar is shown.
    **{kind: Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter for kind in FIT_NARROW_KINDS},
}

# Where 毎回先頭に戻す puts a new page: horizontally centred, at the top.
PAN_TOP_CENTRE = (0.5, 0.0)


def scroll_fraction(bar) -> float | None:
    span = bar.maximum() - bar.minimum()
    return (bar.value() - bar.minimum()) / span if span > 0 else None


# How far fingers travel on a trackpad before a swipe counts as a page turn.
SWIPE_DISTANCE = 40


def delta_direction(horizontal: int, vertical: int) -> int:
    """Rolling down or tilting right moves forward; the roll wins over the tilt."""
    if vertical:
        return 1 if vertical < 0 else -1
    if horizontal:
        return 1 if horizontal > 0 else -1
    return 0


def wheel_direction(event: QWheelEvent) -> int:
    """Turn a wheel roll or a horizontal tilt into a page step.

    Tilting right moves forward and tilting left moves back, matching the
    toolbar's 次へ / 前へ regardless of the reading direction. Touchpads and
    some tilt wheels report pixelDelta only, so both deltas are consulted and
    an event carrying neither yields 0 rather than a stray page turn.
    """
    angles = event.angleDelta()
    pixels = event.pixelDelta()
    return delta_direction(angles.x() or pixels.x(), angles.y() or pixels.y())


class WheelPager:
    """Turns wheel events into page steps, at most one per trackpad swipe.

    A mouse wheel sends one event per notch, and each is a page. A macOS
    trackpad instead streams dozens of small events per swipe, followed by
    momentum events after the fingers lift, so taking each one as a page would
    fly through the folder. Those events carry a scroll phase (a mouse wheel's
    never does, on Windows included), which marks where each swipe begins.
    """

    def __init__(self) -> None:
        self.turned = False
        self.travel_x = 0
        self.travel_y = 0

    def step(self, event: QWheelEvent) -> int:
        phase = event.phase()
        if phase == Qt.ScrollPhase.NoScrollPhase:
            return wheel_direction(event)
        if phase == Qt.ScrollPhase.ScrollBegin:
            self.turned = False
            self.travel_x = self.travel_y = 0
        if phase in (Qt.ScrollPhase.ScrollEnd, Qt.ScrollPhase.ScrollMomentum) or self.turned:
            return 0
        pixels = event.pixelDelta()
        angles = event.angleDelta()
        self.travel_x += pixels.x() or angles.x()
        self.travel_y += pixels.y() or angles.y()
        if max(abs(self.travel_x), abs(self.travel_y)) < SWIPE_DISTANCE:
            return 0
        self.turned = True
        # The dominant axis decides, so a slightly diagonal swipe still reads
        # as the vertical or horizontal move it was meant to be.
        if abs(self.travel_y) >= abs(self.travel_x):
            return delta_direction(0, self.travel_y)
        return delta_direction(self.travel_x, 0)


def format_media_time(milliseconds: int) -> str:
    total_seconds = max(0, milliseconds // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


class SeekSlider(QSlider):
    seek_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__(Qt.Orientation.Horizontal)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            self.seek_to_mouse(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.seek_to_mouse(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.seek_to_mouse(event)
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def seek_to_mouse(self, event: QMouseEvent) -> None:
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
        slider_minimum = groove.left()
        slider_span = max(1, groove.width() - handle.width())
        mouse_position = round(event.position().x() - handle.width() / 2 - slider_minimum)
        value = QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            mouse_position,
            slider_span,
            option.upsideDown,
        )
        self.setValue(value)
        self.seek_requested.emit(value)


class VideoControls(QWidget):
    seek_requested = Signal(int)
    pointer_entered = Signal()
    pointer_left = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "VideoControls { background: rgba(20, 20, 20, 205); border-radius: 8px; }"
            "QLabel { color: white; }"
        )
        self.slider = SeekSlider()
        self.slider.setRange(0, 0)
        self.slider.seek_requested.connect(self.request_seek)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedWidth(112)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.time_label)
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:
        self.pointer_entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.pointer_left.emit()
        super().leaveEvent(event)

    def update_duration(self, duration: int) -> None:
        self.slider.setRange(0, max(0, duration))
        self.update_time(self.slider.value(), duration)

    def update_position(self, position: int, duration: int) -> None:
        if duration > 0 and 0 <= duration - position <= 250:
            position = duration
        self.slider.setValue(position)
        self.update_time(position, duration)

    def update_time(self, position: int, duration: int) -> None:
        self.time_label.setText(
            f"{format_media_time(position)} / {format_media_time(duration)}"
        )

    def request_seek(self, position: int) -> None:
        self.update_time(position, self.slider.maximum())
        self.seek_requested.emit(position)


class ImageView(QGraphicsView):
    navigate = Signal(int)
    fullscreen_requested = Signal()
    context_menu_requested = Signal(QPoint)

    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        # A QGraphicsView takes drops for its scene, which has no use for a
        # file and turns it down, so a file dropped on the picture never
        # reached the window. Switched off, the drop goes up to the window.
        self.setAcceptDrops(False)
        self.pager = WheelPager()
        self.item = QGraphicsPixmapItem()
        self.scene().addItem(self.item)
        # What OCR read, over the picture. A child of the picture, so it moves
        # and zooms with it; render_at_scale keeps its scale in step.
        self.text_overlay = TextOverlay(self.item)
        self.fit_mode = True
        # Which fit Space and a click return to from actual size.
        self.fit_kind = FIT_WINDOW
        self.display_scale = 1.0
        self.source_pixmap = QPixmap()
        # Display-only orientation: mirrored left-right first (if mirrored),
        # then turned clockwise by rotation (0, 90, 180 or 270). These two
        # cover every mix of turns and flips, so presses in any order compose
        # without a growing history. source_pixmap holds the turned picture,
        # so fitting, panning and resampling all work on what is on screen
        # with no cases of their own; the picture as handed in is kept to turn
        # again.
        self.rotation = 0
        self.mirrored = False
        self.unrotated_pixmap = QPixmap()
        self.scaled_cache: OrderedDict[tuple[int, int, int], tuple[QPixmap, int]] = (
            OrderedDict()
        )
        self.scaled_cache_bytes = 0
        self.scaled_cache_limit = 64 * 1024 * 1024
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._left_press_position = None
        self._left_dragged = False

    def set_pixmap(self, pixmap: QPixmap, pan: tuple[float, float] | None = None) -> None:
        """Show a picture, then move to a pan position if one is given.

        None leaves the scroll bars where the previous picture had them.
        """
        self.unrotated_pixmap = pixmap
        if (self.rotation or self.mirrored) and not pixmap.isNull():
            # QTransform applies the call made last first: mirror, then turn.
            transform = QTransform().rotate(self.rotation)
            if self.mirrored:
                transform.scale(-1, 1)
            pixmap = pixmap.transformed(transform)
        self.source_pixmap = pixmap
        # Read from the picture that was on screen: another page, another
        # frame, a turn or a filter all make the positions stale.
        self.text_overlay.set_lines(())
        if self.fit_mode:
            self.fit_to_window()
        else:
            self.render_at_scale(self.display_scale)
        if pan is not None:
            self.set_pan_fraction(*pan)

    def set_orientation(self, rotation: int, mirrored: bool) -> None:
        """Turn or flip the picture on screen; the file itself is never touched.

        The picture may change shape, so the old scroll position means nothing
        on it: it starts again from the top.
        """
        rotation %= 360
        if (rotation, mirrored) == (self.rotation, self.mirrored):
            return
        self.rotation = rotation
        self.mirrored = mirrored
        if not self.unrotated_pixmap.isNull():
            self.set_pixmap(self.unrotated_pixmap, PAN_TOP_CENTRE)

    def rotate(self, degrees: int) -> None:
        self.set_orientation(self.rotation + degrees, self.mirrored)

    def flip_horizontal(self) -> None:
        # Mirroring after a turn equals mirroring first and turning the other way.
        self.set_orientation(-self.rotation, not self.mirrored)

    def flip_vertical(self) -> None:
        # An upside-down flip is a left-right flip turned half way round.
        self.set_orientation(180 - self.rotation, not self.mirrored)

    def reset_orientation(self) -> None:
        """Forget the turn without redrawing: the next set_pixmap shows it upright."""
        self.rotation = 0
        self.mirrored = False

    def pan_fraction(self) -> tuple[float | None, float | None]:
        """How far along each scroll bar the view is, from 0 to 1.

        A proportion rather than pixels, so a position carries over to pages of
        another size or zoom: "the right edge, a third of the way down" means
        the same on every page. None for a side that does not scroll.
        """
        return (
            scroll_fraction(self.horizontalScrollBar()),
            scroll_fraction(self.verticalScrollBar()),
        )

    def set_pan_fraction(self, horizontal: float, vertical: float) -> None:
        for bar, fraction in (
            (self.horizontalScrollBar(), horizontal),
            (self.verticalScrollBar(), vertical),
        ):
            span = bar.maximum() - bar.minimum()
            bar.setValue(bar.minimum() + round(span * min(1.0, max(0.0, fraction))))

    def reset_pan(self) -> None:
        """Start the next picture from its top, centred, instead of where
        the previous one was left scrolled to."""
        self.set_pan_fraction(*PAN_TOP_CENTRE)

    def fit_to_window(self) -> None:
        """Scale the picture by the current fit kind."""
        self.fit_mode = True
        self.setAlignment(FIT_ALIGNMENT[self.fit_kind])
        if not self.source_pixmap.isNull():
            self.render_at_scale(max(0.01, self.fit_scale()))
            self.centre_narrow_fit()

    def set_fit_kind(self, kind: str) -> None:
        self.fit_kind = kind if kind in FIT_KINDS else FIT_WINDOW
        self.fit_to_window()

    def fit_scale(self) -> float:
        """The scale that fits the picture to the view by the current fit kind.

        Measured against the view without scroll bars. Fitting the width of a
        tall picture overflows the height, which brings in a vertical bar that
        takes its width from the view: fitted to the full width, the picture
        would then be a bar's width too wide and gain a horizontal bar as well.
        So the overflowing fits leave room for the bar they cause.
        """
        room = self.maximumViewportSize()
        width = self.source_pixmap.width()
        height = self.source_pixmap.height()
        # The bars' own size hints, which is what the scroll area lays them out
        # at. The style's general PM_ScrollBarExtent matches on Windows but is
        # 4 px short of the real bar on macOS, which left the picture 4 px too
        # wide and brought in a horizontal bar as well.
        if self.fit_kind == FIT_WIDTH:
            scale = room.width() / width
            if height * scale > room.height():
                scale = (room.width() - self.verticalScrollBar().sizeHint().width()) / width
            return scale
        if self.fit_kind == FIT_HEIGHT:
            scale = room.height() / height
            if width * scale > room.width():
                bar = self.horizontalScrollBar().sizeHint().height()
                scale = (room.height() - bar) / height
            return scale
        percent = narrow_percent(self.fit_kind)
        if percent is not None:
            return self.narrow_room_width() * percent / 100 / width
        return min(room.width() / width, room.height() / height)

    def narrow_room_width(self) -> float:
        """The view's width a narrow fit shares out: the whole width, less
        the vertical bar when the fitted picture overflows the height."""
        room = self.maximumViewportSize()
        percent = narrow_percent(self.fit_kind) or 100
        width = self.source_pixmap.width()
        height = self.source_pixmap.height()
        if height * room.width() * percent / 100 / width > room.height():
            return room.width() - self.verticalScrollBar().sizeHint().width()
        return room.width()

    def centre_narrow_fit(self) -> None:
        """Centre a narrow fit by padding the scene's left side by one margin.

        The picture is pinned left, so the padding alone sets where it lands,
        and the padded scene stays narrower than the view, so no horizontal
        bar appears. macOS overlays its bars without taking the view's width,
        and there Qt's own centring lands right while a padded scene does not,
        so it is left to Qt.
        """
        if narrow_percent(self.fit_kind) is None or self.source_pixmap.isNull():
            return
        style = self.style()
        if style.styleHint(QStyle.StyleHint.SH_ScrollBar_Transient, None, self.verticalScrollBar()):
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return
        view_scale = self.transform().m11()
        rect = self.item.boundingRect()
        margin = max(0.0, (self.viewport().width() - rect.width() * view_scale) / 2)
        self.scene().setSceneRect(rect.adjusted(-margin / view_scale, 0, 0, 0))

    def original_size(self) -> None:
        self.fit_mode = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.render_at_scale(1.0)

    def render_at_scale(self, scale: float) -> None:
        if self.source_pixmap.isNull():
            return
        self.display_scale = scale
        self.resetTransform()
        raster_scale = scale
        if scale > 1.0:
            source_cost = self.source_pixmap.width() * self.source_pixmap.height() * 4
            raster_scale = min(scale, max(1.0, sqrt(self.scaled_cache_limit / source_cost)))
        if raster_scale != 1.0:
            width = max(1, round(self.source_pixmap.width() * raster_scale))
            height = max(1, round(self.source_pixmap.height() * raster_scale))
            displayed = self.resampled_pixmap(width, height)
            self.item.setPixmap(displayed)
            remaining_scale = scale / raster_scale
            if remaining_scale != 1.0:
                self.scale(remaining_scale, remaining_scale)
        else:
            self.item.setPixmap(self.source_pixmap)
            self.scale(scale, scale)
        # The overlay is in the source's pixels; the picture item shows the
        # source resampled by this much.
        self.text_overlay.setScale(raster_scale)
        # The picture alone: the overlay's outlines reach a little past it and
        # would otherwise add a sliver of scrolling.
        self.scene().setSceneRect(self.item.boundingRect())

    def resampled_pixmap(self, width: int, height: int) -> QPixmap:
        """Resample the source to an exact pixel size, reusing recent results.

        Qt scales the pixmap in place. Going out to Pillow instead means a round
        trip through QImage.save / Image.open, which encodes and decodes a whole
        PNG per page and costs more than the resampling itself; a smooth Qt
        downscale is box filtered and matches Lanczos to within about 1/255 per
        channel, so nothing visible is given up for it.
        """
        key = (self.source_pixmap.cacheKey(), width, height)
        cached = self.scaled_cache.get(key)
        if cached is not None:
            self.scaled_cache.move_to_end(key)
            return cached[0]
        pixmap = self.source_pixmap.scaled(
            width,
            height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        cost = width * height * 4
        self.scaled_cache[key] = (pixmap, cost)
        self.scaled_cache_bytes += cost
        while self.scaled_cache_bytes > self.scaled_cache_limit:
            _old_key, (_old_pixmap, old_cost) = self.scaled_cache.popitem(last=False)
            self.scaled_cache_bytes -= old_cost
        return pixmap

    def toggle_fit(self) -> None:
        self.original_size() if self.fit_mode else self.fit_to_window()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.fit_mode = False
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            target = self.display_scale * factor
            if 0.1 <= target <= 8:
                self.render_at_scale(target)
            event.accept()
            return
        direction = self.pager.step(event)
        if direction:
            self.navigate.emit(direction)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self.fullscreen_requested.emit()
            event.accept()
            return
        if event.button() in PAGE_BUTTONS:
            self.navigate.emit(PAGE_BUTTONS[event.button()])
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._left_press_position = event.position().toPoint()
            self._left_dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._left_press_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            distance = (event.position().toPoint() - self._left_press_position).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._left_dragged = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        was_click = (
            event.button() == Qt.MouseButton.LeftButton
            and self._left_press_position is not None
            and not self._left_dragged
        )
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._left_press_position = None
            self._left_dragged = False
        if was_click:
            self.toggle_fit()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._left_press_position = None
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.context_menu_requested.emit(event.globalPos())
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.fit_mode:
            self.fit_to_window()


class VideoView(QWidget):
    navigate = Signal(int)
    fullscreen_requested = Signal()
    play_pause_requested = Signal()
    volume_change_requested = Signal(int)
    seek_requested = Signal(int)
    context_menu_requested = Signal(QPoint)

    def __init__(self) -> None:
        super().__init__()
        self.video_duration = 0
        self.pager = WheelPager()
        self.setStyleSheet("background: black;")
        self.surface = QVideoWidget(self)
        self.surface.setMouseTracking(True)
        self.surface.installEventFilter(self)
        # The video widget draws through an inner widget that accepts drops and
        # then ignores them; as with ImageView, the window should get the file.
        for child in self.surface.findChildren(QWidget):
            child.setAcceptDrops(False)
        self.controls = VideoControls(self)
        self.controls.seek_requested.connect(self.seek_requested)
        self.controls.pointer_entered.connect(self.show_video_controls)
        self.controls.pointer_left.connect(self.schedule_controls_hide)
        self.controls_opacity = QGraphicsOpacityEffect(self.controls)
        self.controls.setGraphicsEffect(self.controls_opacity)
        self.controls_animation = QPropertyAnimation(self.controls_opacity, b"opacity", self)
        self.controls_animation.setDuration(400)
        self.controls_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.controls_animation.finished.connect(self.finish_controls_fade)
        self.controls_hide_timer = QTimer(self)
        self.controls_hide_timer.setSingleShot(True)
        self.controls_hide_timer.setInterval(5000)
        self.controls_hide_timer.timeout.connect(self.fade_video_controls)
        self.pointer_timer = QTimer(self)
        self.pointer_timer.setInterval(150)
        self.pointer_timer.timeout.connect(self.check_pointer_position)
        self.pointer_timer.start()
        self.controls_opacity.setOpacity(0.0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.surface, 1)
        layout.addWidget(self.controls)

    def update_duration(self, duration: int) -> None:
        self.video_duration = max(0, duration)
        self.controls.update_duration(duration)

    def prepare_media(self) -> None:
        self.video_duration = 0
        self.controls.slider.setValue(0)
        self.controls.update_duration(0)

    def update_position(self, position: int) -> None:
        self.controls.update_position(position, self.video_duration)

    def frame_pixmap(self) -> QPixmap:
        """Grab the frame on screen so it can become a favorite thumbnail."""
        sink = self.surface.videoSink()
        if sink is not None:
            image = sink.videoFrame().toImage()
            if not image.isNull():
                return QPixmap.fromImage(image)
        return self.surface.grab()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.context_menu_requested.emit(event.globalPos())
        event.accept()

    def show_video_controls(self) -> None:
        self.controls_hide_timer.stop()
        self.controls_animation.stop()
        self.controls_opacity.setOpacity(1.0)

    def schedule_controls_hide(self) -> None:
        if self.controls_opacity.opacity() > 0.0:
            self.controls_hide_timer.start()

    def fade_video_controls(self) -> None:
        if self.controls_opacity.opacity() <= 0.0:
            return
        self.controls_animation.stop()
        self.controls_animation.setStartValue(self.controls_opacity.opacity())
        self.controls_animation.setEndValue(0.0)
        self.controls_animation.start()

    def finish_controls_fade(self) -> None:
        if self.controls_animation.endValue() == 0.0:
            self.controls_opacity.setOpacity(0.0)

    def activate_controls(self) -> None:
        self.show_video_controls()
        self.controls_hide_timer.start()

    def check_pointer_position(self) -> None:
        if not self.isVisible() or self.surface.height() <= 0:
            return
        position = self.surface.mapFromGlobal(QCursor.pos())
        controls_position = self.controls.mapFromGlobal(QCursor.pos())
        if self.controls.rect().contains(controls_position) or (
            self.surface.rect().contains(position)
            and position.y() >= self.surface.height() - 120
        ):
            self.show_video_controls()

    def eventFilter(self, watched, event) -> bool:
        if watched is not self.surface:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseMove:
            if event.position().y() >= self.surface.height() - 120:
                self.show_video_controls()
            else:
                self.schedule_controls_hide()
        elif event.type() == QEvent.Type.Leave:
            self.schedule_controls_hide()
        elif event.type() == QEvent.Type.ContextMenu:
            self.context_menu_requested.emit(event.globalPos())
            event.accept()
            return True
        elif event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.volume_change_requested.emit(5 if event.angleDelta().y() > 0 else -5)
            else:
                direction = self.pager.step(event)
                if direction:
                    self.navigate.emit(direction)
            event.accept()
            return True
        elif event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.MiddleButton:
                self.fullscreen_requested.emit()
                event.accept()
                return True
            if event.button() in PAGE_BUTTONS:
                self.navigate.emit(PAGE_BUTTONS[event.button()])
                event.accept()
                return True
            if event.button() == Qt.MouseButton.LeftButton:
                self.play_pause_requested.emit()
                event.accept()
                return True
        return super().eventFilter(watched, event)
