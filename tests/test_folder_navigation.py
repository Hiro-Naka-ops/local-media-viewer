from pathlib import Path
from time import perf_counter

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

import local_media_viewer.app as app_module
from local_media_viewer.filmstrip import Filmstrip
from local_media_viewer.settings import ViewerSettings


def save_image(path: Path, color: str) -> None:
    Image.new("RGB", (12, 8), color).save(path)


def wait_for_thumbnail(qt_app: QApplication, filmstrip: Filmstrip, index: int) -> bool:
    """Pump the loop until a thumbnail arrives from the loader threads."""
    filmstrip.visible_timer.stop()
    filmstrip.request_visible_thumbnails()
    deadline = perf_counter() + 5.0
    while perf_counter() < deadline:
        qt_app.processEvents()
        icon = filmstrip.icon_for(index)
        if icon is not None and not icon.isNull():
            return True
    return False


def test_folder_boundary_navigation_displays_target_image(
    tmp_path: Path, monkeypatch
) -> None:
    qt_app = QApplication.instance() or QApplication([])
    previous = tmp_path / "1"
    empty = tmp_path / "2"
    current = tmp_path / "3"
    following = tmp_path / "4"
    for folder in (previous, empty, current, following):
        folder.mkdir()
    save_image(previous / "previous.png", "red")
    save_image(current / "current.png", "green")
    save_image(following / "following.png", "blue")

    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window = app_module.MainWindow()
    try:
        window.open_path(current / "current.png")
        assert window.filmstrip.model.rowCount() == 1
        # Thumbnails are decoded off the UI thread, so they land after a turn
        # of the event loop rather than during open_path.
        assert wait_for_thumbnail(qt_app, window.filmstrip, 0)
        window.navigate(-1)
        assert window.current_folder == previous
        assert window.files[window.index].name == "previous.png"
        assert not window.image_view.item.pixmap().isNull()

        window.open_path(current / "current.png")
        window.navigate(1)
        assert window.current_folder == following
        assert window.files[window.index].name == "following.png"
        assert not window.image_view.item.pixmap().isNull()
        assert window.filmstrip.current == 0
        assert window.filmstrip.view.currentIndex().row() == 0
        qt_app.processEvents()
    finally:
        window.close()
