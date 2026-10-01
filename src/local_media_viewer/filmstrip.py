from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QIcon, QImage, QImageReader, QPixmap, QWheelEvent
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QListView, QWidget

from local_media_viewer import heic  # noqa: F401  (registers the HEIC decoder)
from local_media_viewer.media import PDF_EXTENSIONS, VIDEO_EXTENSIONS
from local_media_viewer.pdfview import read_first_page

THUMBNAIL_SIZE = QSize(88, 62)
ITEM_SIZE = QSize(104, 88)
GRID_SIZE = QSize(110, 94)
# Thumbnails kept in view on each side of the current one, so the next and
# previous few pages can be seen coming while paging through.
LOOKAHEAD = 3

FILMSTRIP_STYLE = """
QListView {
    background: #1D1D1D;
    border: none;
    outline: none;
    color: white;
}
QListView::item {
    background: #292929;
    border: 1px solid #555555;
    color: white;
}
QListView::item:hover { background: #3A3A3A; }
QListView::item:selected { background: #292929; border: 3px solid #F79009; }
"""


def read_thumbnail(path: Path) -> QImage:
    """Decode one thumbnail, letting the codec do the shrinking.

    setScaledSize before read lets a JPEG decode straight to a reduced size
    instead of unpacking the full frame first, which is most of the saving.
    QImage is used rather than QPixmap because this runs off the UI thread,
    where QPixmap is not allowed.
    """
    if path.suffix.lower() in PDF_EXTENSIONS:
        return read_first_page(path, THUMBNAIL_SIZE)
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        size.scale(THUMBNAIL_SIZE, Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(size)
    image = reader.read()
    if image.isNull():
        # Qt has no decoder for some formats (HEIC on Windows); Pillow does.
        image = read_thumbnail_with_pillow(path)
    return image


def read_thumbnail_with_pillow(path: Path) -> QImage:
    try:
        with Image.open(path) as source:
            source.thumbnail((THUMBNAIL_SIZE.width(), THUMBNAIL_SIZE.height()))
            # copy() detaches the QImage from the buffer ImageQt keeps alive.
            return ImageQt(source.convert("RGBA")).copy()
    except (OSError, ValueError):
        return QImage()


class ThumbnailLoader(QObject):
    """Decodes thumbnails in worker threads and delivers them to the UI thread."""

    ready = Signal(int, QImage)

    def __init__(self, workers: int = 4) -> None:
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="thumb")
        # Bumped on every new folder so results from the previous one, which are
        # already in flight and cannot be cancelled mid-decode, are dropped.
        self.generation = 0
        self.closed = False

    def reset(self) -> None:
        self.generation += 1

    def request(self, row: int, path: Path) -> None:
        # A scroll or resize already queued when the window closed can still
        # ask for thumbnails; the executor would raise, and nobody is looking.
        if self.closed:
            return
        self._executor.submit(self._work, self.generation, row, path)

    def _work(self, generation: int, row: int, path: Path) -> None:
        if generation != self.generation:
            return
        try:
            image = read_thumbnail(path)
        except (OSError, ValueError):
            return
        if generation == self.generation and not self.closed and not image.isNull():
            # Queued across threads by Qt, so the icon lands on the UI thread.
            self.ready.emit(row, image)

    def close(self) -> None:
        """Stop, waiting for any thumbnail already being decoded.

        Not waiting let the loader be destroyed while a worker was still
        inside it, which crashed the process (reproduced on Windows by closing
        and collecting a strip straight after it asked for thumbnails; on the
        Mac CI it killed the test run). The wait is at most one thumbnail per
        worker, a few milliseconds.
        """
        self.closed = True
        self.generation += 1
        self._executor.shutdown(wait=True, cancel_futures=True)


class FilmstripModel(QAbstractListModel):
    """Holds the folder listing and whichever thumbnails have arrived so far."""

    def __init__(self) -> None:
        super().__init__()
        self.files: list[Path] = []
        self.icons: dict[int, QIcon] = {}
        self.labels: list[str] = []

    def set_files(self, files: list[Path]) -> None:
        self.beginResetModel()
        self.files = list(files)
        self.icons.clear()
        self.labels = [self._label(path) for path in self.files]
        self.endResetModel()

    def set_icon(self, row: int, icon: QIcon) -> None:
        if 0 <= row < len(self.files):
            self.icons[row] = icon
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.files)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int) -> object:
        row = index.row()
        if not 0 <= row < len(self.files):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.labels[row]
        if role == Qt.ItemDataRole.DecorationRole:
            return self.icons.get(row)
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(self.files[row])
        if role == Qt.ItemDataRole.SizeHintRole:
            return ITEM_SIZE
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
        return None

    @staticmethod
    def _label(path: Path) -> str:
        name = path.name if len(path.name) <= 14 else f"{path.name[:11]}…"
        return f"▶ {name}" if path.suffix.lower() in VIDEO_EXTENSIONS else name


class FilmstripView(QListView):
    def wheelEvent(self, event: QWheelEvent) -> None:
        pixels = event.pixelDelta()
        if not pixels.isNull():
            delta = pixels.y() if pixels.y() else pixels.x()
            self.scroll_horizontal(delta)
        else:
            angles = event.angleDelta()
            delta = angles.y() if angles.y() else angles.x()
            step = max(40, self.horizontalScrollBar().singleStep() * 3)
            self.scroll_horizontal(round(delta / 120 * step))
        event.accept()

    def scroll_horizontal(self, delta: int) -> None:
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - delta)


class Filmstrip(QWidget):
    selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.requested: set[int] = set()
        self.current = -1
        self.setFixedHeight(112)
        self.setStyleSheet("background: #1D1D1D;")

        self.model = FilmstripModel()
        # A QListView builds only the rows on screen. A widget per file laid the
        # whole folder out on every open, which is what made a large folder take
        # seconds to appear.
        self.view = FilmstripView()
        self.view.setModel(self.model)
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setFlow(QListView.Flow.LeftToRight)
        self.view.setWrapping(False)
        self.view.setUniformItemSizes(True)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setIconSize(THUMBNAIL_SIZE)
        self.view.setGridSize(GRID_SIZE)
        self.view.setSpacing(0)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setStyleSheet(FILMSTRIP_STYLE)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.clicked.connect(self._emit_selected)
        self.view.horizontalScrollBar().valueChanged.connect(self.schedule_visible_thumbnails)

        self.loader = ThumbnailLoader()
        self.loader.ready.connect(self.apply_thumbnail)
        # Scrolling fires continuously, so the requests it triggers are coalesced.
        self.visible_timer = QTimer(self)
        self.visible_timer.setSingleShot(True)
        self.visible_timer.setInterval(60)
        self.visible_timer.timeout.connect(self.request_visible_thumbnails)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

    @property
    def files(self) -> list[Path]:
        return self.model.files

    def set_files(self, files: list[Path]) -> None:
        if files == self.model.files:
            return
        self.loader.reset()
        self.requested.clear()
        self.current = -1
        self.model.set_files(files)
        self.schedule_visible_thumbnails()

    def set_current(self, index: int) -> None:
        self.current = index
        if 0 <= index < self.model.rowCount():
            model_index = self.model.index(index, 0)
            self.view.setCurrentIndex(model_index)
            self.keep_in_view(model_index)
        else:
            self.view.clearSelection()
        self.schedule_visible_thumbnails()

    def keep_in_view(self, model_index: QModelIndex) -> None:
        """Scroll just enough to show LOOKAHEAD thumbnails either side of this one.

        EnsureVisible stops as soon as the item itself is on screen, so paging
        forward pinned the current thumbnail to the edge with nothing visible
        past it. Scrolling only when the margin runs out, rather than always
        centring, keeps the strip still while the current one moves inside it.
        """
        width = self.view.viewport().width()
        rect = self.view.visualRect(model_index)
        if width <= 0 or not rect.isValid():
            self.view.scrollTo(model_index, QListView.ScrollHint.EnsureVisible)
            return
        margin = LOOKAHEAD * GRID_SIZE.width()
        # Too narrow for the full margin: share what room there is equally.
        margin = min(margin, max(0, (width - rect.width()) // 2))
        bar = self.view.horizontalScrollBar()
        if rect.left() - margin < 0:
            bar.setValue(bar.value() + rect.left() - margin)
        elif rect.right() + 1 + margin > width:
            bar.setValue(bar.value() + rect.right() + 1 + margin - width)

    def schedule_visible_thumbnails(self) -> None:
        if self.model.rowCount():
            self.visible_timer.start()

    def visible_range(self) -> tuple[int, int]:
        """Which rows are on screen, padded so a short scroll finds them ready."""
        count = self.model.rowCount()
        if not count:
            return (0, 0)
        step = max(1, GRID_SIZE.width())
        left = self.view.horizontalScrollBar().value()
        width = self.view.viewport().width() or self.width()
        first = max(0, left // step - 6)
        last = min(count, (left + width) // step + 7)
        return (first, max(first, last))

    def request_visible_thumbnails(self) -> None:
        first, last = self.visible_range()
        for row in range(first, last):
            if row in self.requested:
                continue
            path = self.model.files[row]
            if path.suffix.lower() in VIDEO_EXTENSIONS:
                continue
            self.requested.add(row)
            self.loader.request(row, path)

    def apply_thumbnail(self, row: int, image: QImage) -> None:
        pixmap = QPixmap.fromImage(image)
        icon = QIcon()
        # The same pixmap is registered for every state: left to itself Qt tints
        # the icon of the selected row with the highlight colour, which would
        # misreport the colours of the page being looked at.
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active):
            icon.addPixmap(pixmap, mode, QIcon.State.Off)
            icon.addPixmap(pixmap, mode, QIcon.State.On)
        self.model.set_icon(row, icon)

    def icon_for(self, row: int) -> QIcon | None:
        return self.model.icons.get(row)

    def closeEvent(self, event) -> None:
        self.loader.close()
        super().closeEvent(event)

    def _emit_selected(self, index: QModelIndex) -> None:
        if index.isValid():
            self.selected.emit(index.row())
