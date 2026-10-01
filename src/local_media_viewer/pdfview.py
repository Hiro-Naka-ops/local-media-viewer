"""A PDF shown as one long column of pages, scrolled with the wheel.

Qt's own PDF view (PDFium underneath) does the drawing: it renders only the
pages in sight, at the zoom in use, so a long document opens at once and
stays sharp when enlarged. That also means the picture pipeline (filters,
effects, rotation, spreads, enhancement) never sees a PDF; like a video, it
is shown as it is.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QContextMenuEvent, QImage, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView

from local_media_viewer.viewer import PAGE_BUTTONS

# The gap between pages. Qt's default of 3 px reads as one unbroken sheet;
# this is wide enough to tell at a glance where a page ends.
PAGE_SPACING = 18
ZOOM_STEP = 1.15
ZOOM_RANGE = (0.1, 8.0)
POINTS_PER_INCH = 72


def render_page(document: QPdfDocument, page: int, bounds: QSize) -> QImage:
    """One page fitted inside `bounds`, on white.

    PDFium leaves the paper transparent, which shows as black in a thumbnail.
    """
    size = document.pagePointSize(page).toSize()
    if size.isEmpty():
        return QImage()
    size.scale(bounds, Qt.AspectRatioMode.KeepAspectRatio)
    page_image = document.render(page, size)
    if page_image.isNull():
        return QImage()
    image = QImage(page_image.size(), QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.drawImage(0, 0, page_image)
    painter.end()
    return image


def read_first_page(path: Path, bounds: QSize) -> QImage:
    """The first page as a thumbnail; a null image when the file cannot be read.

    Opens a document of its own, so it can run on a thumbnail worker thread
    while the view has the same file open.
    """
    document = QPdfDocument()
    try:
        if document.load(str(path)) != QPdfDocument.Error.None_ or document.pageCount() < 1:
            return QImage()
        return render_page(document, 0, bounds)
    finally:
        document.close()


class PdfView(QPdfView):
    navigate = Signal(int)
    fullscreen_requested = Signal()
    context_menu_requested = Signal(QPoint)
    # The page at the top of the view changed (or another document opened).
    page_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.pdf = QPdfDocument(self)
        self.setDocument(self.pdf)
        self.setPageMode(QPdfView.PageMode.MultiPage)
        self.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.setPageSpacing(PAGE_SPACING)
        self.pageNavigator().currentPageChanged.connect(lambda _page: self.page_changed.emit())

    def open(self, path: Path) -> bool:
        """Shows `path` from its first page. False when it cannot be opened
        (damaged, not a PDF, or locked with a password)."""
        self.pdf.close()
        if self.pdf.load(str(path)) != QPdfDocument.Error.None_:
            self.pdf.close()
            return False
        self.verticalScrollBar().setValue(0)
        self.horizontalScrollBar().setValue(0)
        self.page_changed.emit()
        return True

    def close_document(self) -> None:
        # Also lets go of the file, which Windows keeps locked while it is open.
        self.pdf.close()

    def page_count(self) -> int:
        return self.pdf.pageCount()

    def current_page(self) -> int:
        return self.pageNavigator().currentPage()

    def page_image(self, bounds: QSize) -> QImage:
        """The page being read, for a favorite's thumbnail."""
        if self.page_count() < 1:
            return QImage()
        return render_page(self.pdf, max(0, self.current_page()), bounds)

    def fits_width(self) -> bool:
        return self.zoomMode() == QPdfView.ZoomMode.FitToWidth

    def fits_page(self) -> bool:
        return self.zoomMode() == QPdfView.ZoomMode.FitInView

    def fit_width(self) -> None:
        self.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def fit_page(self) -> None:
        self.setZoomMode(QPdfView.ZoomMode.FitInView)

    def toggle_fit(self) -> None:
        self.fit_page() if self.fits_width() else self.fit_width()

    def set_zoom(self, factor: float) -> None:
        low, high = ZOOM_RANGE
        self.setZoomMode(QPdfView.ZoomMode.Custom)
        self.setZoomFactor(min(high, max(low, factor)))

    def effective_zoom(self) -> float:
        """The zoom on screen. zoomFactor() only holds it in custom mode; in
        the two fitting modes Qt works the scale out for itself and keeps it
        private, so it is worked out again here the same way."""
        if self.zoomMode() == QPdfView.ZoomMode.Custom or self.page_count() < 1:
            return self.zoomFactor()
        page = self.pdf.pagePointSize(max(0, self.current_page()))
        if page.isEmpty():
            return self.zoomFactor()
        margins = self.documentMargins()
        scale = self.logicalDpiX() / POINTS_PER_INCH
        across = (self.viewport().width() - margins.left() - margins.right()) / (
            page.width() * scale
        )
        if self.fits_width():
            return across
        down = (self.viewport().height() - margins.top() - margins.bottom()) / (
            page.height() * scale
        )
        return min(across, down)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
            self.set_zoom(self.effective_zoom() * step)
            event.accept()
            return
        # Unlike a picture, where the wheel turns to the next file, a PDF is
        # read by scrolling down its pages.
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self.fullscreen_requested.emit()
            event.accept()
            return
        if event.button() in PAGE_BUTTONS:
            self.navigate.emit(PAGE_BUTTONS[event.button()])
            event.accept()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self.context_menu_requested.emit(event.globalPos())
        event.accept()
