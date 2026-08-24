from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

import local_media_viewer.app as app_module
from local_media_viewer.settings import ViewerSettings


def save_image(path: Path, color: str) -> None:
    Image.new("RGB", (12, 8), color).save(path)


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
        assert len(window.filmstrip.buttons) == 1
        assert window.filmstrip.buttons[0].icon().isNull() is False
        window.navigate(-1)
        assert window.current_folder == previous
        assert window.files[window.index].name == "previous.png"
        assert not window.image_view.item.pixmap().isNull()

        window.open_path(current / "current.png")
        window.navigate(1)
        assert window.current_folder == following
        assert window.files[window.index].name == "following.png"
        assert not window.image_view.item.pixmap().isNull()
        assert "3px solid #F79009" in window.filmstrip.buttons[0].styleSheet()
        qt_app.processEvents()
    finally:
        window.close()
