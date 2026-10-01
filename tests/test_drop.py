from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.settings import ViewerSettings


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def drop(window, widget, path: Path) -> None:
    """Drop `path` on the middle of `widget`, the way a real drag arrives.

    Sent to the window handle, so Qt itself picks the widget that gets it: a
    child that takes drops and turns them down stops the window seeing them,
    which calling the window's dropEvent directly would never show.
    """
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    position = widget.mapTo(window, widget.rect().center())
    details = (
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    handle = window.windowHandle()
    QApplication.sendEvent(handle, QDragEnterEvent(position, *details))
    QApplication.sendEvent(handle, QDragMoveEvent(position, *details))
    QApplication.sendEvent(handle, QDropEvent(QPointF(position), *details))
    QApplication.instance().processEvents()


@pytest.mark.parametrize("area", ["image_view", "video_view", "pdf_view", "filmstrip", "toolbar"])
def test_a_file_dropped_anywhere_on_the_window_opens(tmp_path: Path, monkeypatch, area) -> None:
    (tmp_path / "book").mkdir()
    Image.new("RGB", (20, 20), "red").save(tmp_path / "book" / "a.png")
    Image.new("RGB", (20, 20), "blue").save(tmp_path / "other.png")
    window = make_window(monkeypatch)
    try:
        window.resize(900, 700)
        window.show()
        window.open_path(tmp_path / "book" / "a.png")
        target = getattr(window, area)
        if target in (window.video_view, window.pdf_view):
            # Whichever view is up front is the one under the pointer.
            window.stack.setCurrentWidget(target)
        QApplication.instance().processEvents()

        drop(window, target, tmp_path / "other.png")

        assert window.files[window.index] == tmp_path / "other.png"
        assert window.stack.currentWidget() is window.image_view
    finally:
        window.close()


def test_a_dropped_folder_opens_at_its_first_file(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "book").mkdir()
    for name in ("1.png", "2.png"):
        Image.new("RGB", (20, 20)).save(tmp_path / "book" / name)
    window = make_window(monkeypatch)
    try:
        window.show()
        QApplication.instance().processEvents()
        drop(window, window.image_view, tmp_path / "book")
        assert window.files[window.index] == tmp_path / "book" / "1.png"
    finally:
        window.close()
