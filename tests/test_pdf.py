from pathlib import Path
from time import monotonic

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QPageSize, QPainter, QPdfWriter, QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox

import local_media_viewer.app as app_module
from local_media_viewer import pdfview
from local_media_viewer.filmstrip import THUMBNAIL_SIZE, read_thumbnail
from local_media_viewer.media import media_files
from local_media_viewer.settings import ViewerSettings
from local_media_viewer.viewer import FIT_WIDTH, FIT_WINDOW


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def make_pdf(path: Path, pages: int = 5) -> Path:
    QApplication.instance() or QApplication([])
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A5))
    painter = QPainter(writer)
    for number in range(pages):
        if number:
            writer.newPage()
        painter.drawText(200, 400, f"page {number + 1}")
    painter.end()
    return path


def wait_for(condition, seconds: float = 5.0) -> None:
    app = QApplication.instance()
    deadline = monotonic() + seconds
    while not condition():
        assert monotonic() < deadline, "timed out"
        app.processEvents()


def wheel(view, delta: int, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    centre = QPointF(view.viewport().rect().center())
    event = QWheelEvent(
        centre,
        QPointF(view.viewport().mapToGlobal(centre.toPoint())),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(view.viewport(), event)


def test_a_pdf_is_listed_with_the_pictures(tmp_path: Path) -> None:
    Image.new("RGB", (8, 8)).save(tmp_path / "1.png")
    make_pdf(tmp_path / "2.pdf")
    (tmp_path / "3.txt").write_text("no")
    assert [path.name for path in media_files(tmp_path)] == ["1.png", "2.pdf"]


def test_a_pdf_opens_as_one_column_scrolled_by_the_wheel(tmp_path: Path, monkeypatch) -> None:
    make_pdf(tmp_path / "book.pdf")
    Image.new("RGB", (8, 8)).save(tmp_path / "z.png")
    window = make_window(monkeypatch)
    try:
        window.resize(700, 600)
        window.show()
        window.open_path(tmp_path / "book.pdf")
        view = window.pdf_view
        wait_for(lambda: view.verticalScrollBar().maximum() > 0)

        assert window.stack.currentWidget() is view
        assert view.page_count() == 5
        assert view.pageMode() == view.PageMode.MultiPage
        assert view.pageSpacing() == pdfview.PAGE_SPACING
        assert "1 / 5 ページ" in window.statusBar().currentMessage()

        # The wheel moves down the pages; it does not turn to the next file.
        wheel(view, -120)
        assert view.verticalScrollBar().value() > 0
        assert window.index == 0

        view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
        wait_for(lambda: view.current_page() == 4)
        assert "5 / 5 ページ" in window.statusBar().currentMessage()

        # The picture-only tools are off, as they are for a video.
        assert not window.enhance_action.isEnabled()
        assert not window.orientation_menu.isEnabled()

        # Left and Right still change file; Up and Down are left to scroll.
        assert [s.toString() for s in window.next_action.shortcuts()] == ["Right"]
        window.next_action.trigger()
        assert window.stack.currentWidget() is window.image_view
        assert [s.toString() for s in window.next_action.shortcuts()] == ["Right", "Down"]
        # Let go of, so the file is not left locked.
        assert view.page_count() == 0
    finally:
        window.close()


def test_a_reopened_pdf_starts_from_the_top(tmp_path: Path, monkeypatch) -> None:
    make_pdf(tmp_path / "a.pdf")
    make_pdf(tmp_path / "b.pdf")
    window = make_window(monkeypatch)
    try:
        window.resize(700, 600)
        window.show()
        window.open_path(tmp_path / "a.pdf")
        view = window.pdf_view
        wait_for(lambda: view.verticalScrollBar().maximum() > 0)
        view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())

        window.next_action.trigger()
        wait_for(lambda: view.verticalScrollBar().maximum() > 0)

        assert window.files[window.index].name == "b.pdf"
        assert view.verticalScrollBar().value() == 0
        assert "1 / 5 ページ" in window.statusBar().currentMessage()
    finally:
        window.close()


def test_size_choices_and_ctrl_wheel_zoom_a_pdf(tmp_path: Path, monkeypatch) -> None:
    make_pdf(tmp_path / "book.pdf")
    window = make_window(monkeypatch)
    try:
        window.resize(700, 600)
        window.show()
        window.open_path(tmp_path / "book.pdf")
        view = window.pdf_view
        wait_for(lambda: view.verticalScrollBar().maximum() > 0)
        assert view.fits_width()
        window.show_size_state()
        assert window.size_actions[FIT_WIDTH].isChecked()

        window.fit_action.trigger()  # Space
        assert view.fits_page()
        window.show_size_state()
        assert window.size_actions[FIT_WINDOW].isChecked()

        window.choose_size(app_module.ACTUAL_SIZE)
        assert view.zoomFactor() == 1.0
        assert window.size_actions[app_module.ACTUAL_SIZE].isChecked()

        # Zooming starts from the size on screen, not from a stale factor.
        window.choose_size(FIT_WIDTH)
        fitted = view.effective_zoom()
        wheel(view, 120, Qt.KeyboardModifier.ControlModifier)
        assert abs(view.zoomFactor() - fitted * pdfview.ZOOM_STEP) < 0.01
        # The choice for pictures is untouched.
        assert window.image_view.fit_kind == FIT_WINDOW
    finally:
        window.close()


def test_a_file_that_is_not_a_pdf_says_so(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, title, text: warned.append(title))
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "broken.pdf")
        assert warned == ["PDFを開けません"]
        assert window.pdf_view.page_count() == 0
    finally:
        window.close()


def test_the_thumbnail_is_the_first_page_on_white(tmp_path: Path) -> None:
    make_pdf(tmp_path / "book.pdf")

    image = read_thumbnail(tmp_path / "book.pdf")

    assert not image.isNull()
    assert image.width() <= THUMBNAIL_SIZE.width() and image.height() == THUMBNAIL_SIZE.height()
    # PDFium leaves the paper transparent, which would show as black.
    assert image.pixelColor(1, 1).name() == "#ffffff"
    assert pdfview.read_first_page(tmp_path / "missing.pdf", QSize(50, 50)).isNull()


def test_a_favorite_thumbnail_shows_the_page_being_read(tmp_path: Path, monkeypatch) -> None:
    make_pdf(tmp_path / "book.pdf")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "book.pdf")
        thumbnail = window.current_thumbnail()
        assert not thumbnail.isNull()
        assert max(thumbnail.width(), thumbnail.height()) == 512
    finally:
        window.close()
