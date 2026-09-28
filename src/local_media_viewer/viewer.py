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


# Drivers commonly map a tilt wheel onto the back/forward side buttons, so
# those turn pages too.
PAGE_BUTTONS = {
    Qt.MouseButton.BackButton: -1,
    Qt.MouseButton.ForwardButton: 1,
}


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
        self.pager = WheelPager()
        self.item = QGraphicsPixmapItem()
        self.scene().addItem(self.item)
        self.fit_mode = True
        self.display_scale = 1.0
        self.source_pixmap = QPixmap()
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

    def set_pixmap(self, pixmap: QPixmap, reset_pan: bool = False) -> None:
        self.source_pixmap = pixmap
        if self.fit_mode:
            self.fit_to_window()
        else:
            self.render_at_scale(self.display_scale)
        if reset_pan:
            self.reset_pan()

    def reset_pan(self) -> None:
        """Start the next picture from its top, centred, instead of where
        the previous one was left scrolled to."""
        horizontal = self.horizontalScrollBar()
        horizontal.setValue((horizontal.minimum() + horizontal.maximum()) // 2)
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())

    def fit_to_window(self) -> None:
        self.fit_mode = True
        if not self.source_pixmap.isNull():
            viewport = self.viewport().size()
            scale = min(
                viewport.width() / self.source_pixmap.width(),
                viewport.height() / self.source_pixmap.height(),
            )
            self.render_at_scale(max(0.01, scale))

    def original_size(self) -> None:
        self.fit_mode = False
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
