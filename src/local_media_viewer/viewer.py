from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView


class ImageView(QGraphicsView):
    navigate = Signal(int)
    fullscreen_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.item = QGraphicsPixmapItem()
        self.scene().addItem(self.item)
        self.fit_mode = True
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._left_press_position = None
        self._left_dragged = False

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.item.setPixmap(pixmap)
        self.scene().setSceneRect(self.item.boundingRect())
        if self.fit_mode:
            self.fit_to_window()

    def fit_to_window(self) -> None:
        self.fit_mode = True
        self.resetTransform()
        if not self.item.pixmap().isNull():
            self.fitInView(self.item, Qt.AspectRatioMode.KeepAspectRatio)

    def original_size(self) -> None:
        self.fit_mode = False
        self.resetTransform()

    def toggle_fit(self) -> None:
        self.original_size() if self.fit_mode else self.fit_to_window()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.fit_mode = False
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            current = self.transform().m11()
            if 0.1 <= current * factor <= 8:
                self.scale(factor, factor)
            event.accept()
            return
        self.navigate.emit(1 if event.angleDelta().y() < 0 else -1)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self.fullscreen_requested.emit()
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

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.fit_mode:
            self.fit_to_window()


class VideoView(QVideoWidget):
    navigate = Signal(int)
    fullscreen_requested = Signal()
    play_pause_requested = Signal()
    volume_change_requested = Signal(int)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.volume_change_requested.emit(5 if event.angleDelta().y() > 0 else -5)
            event.accept()
            return
        self.navigate.emit(1 if event.angleDelta().y() < 0 else -1)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self.fullscreen_requested.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.play_pause_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)
