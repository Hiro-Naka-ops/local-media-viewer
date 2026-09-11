from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.app import MainWindow
from local_media_viewer.settings import ViewerSettings


def save_image(path: Path, color: str) -> None:
    Image.new("RGB", (24, 24), color).save(path)


def test_arrow_keys_navigate_media(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("local_media_viewer.app.save_settings", lambda _settings: None)
    # Defaults only: the real settings.json would otherwise decide whether
    # an arrow key steps one page or a two-page spread.
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    app = QApplication.instance() or QApplication([])
    first = tmp_path / "1.png"
    second = tmp_path / "2.png"
    third = tmp_path / "3.png"
    save_image(first, "red")
    save_image(second, "green")
    save_image(third, "blue")

    window = MainWindow(first)
    window.show()
    app.processEvents()

    QTest.keyClick(window.image_view.viewport(), Qt.Key.Key_Right)
    assert window.files[window.index] == second
    QTest.keyClick(window.image_view.viewport(), Qt.Key.Key_Down)
    assert window.files[window.index] == third
    QTest.keyClick(window.image_view.viewport(), Qt.Key.Key_Left)
    assert window.files[window.index] == second
    QTest.keyClick(window.image_view.viewport(), Qt.Key.Key_Up)
    assert window.files[window.index] == first

    window.close()


def test_space_toggles_fit_and_enter_toggles_fullscreen(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("local_media_viewer.app.save_settings", lambda _settings: None)
    # Defaults only: the real settings.json would otherwise decide whether
    # an arrow key steps one page or a two-page spread.
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    image = tmp_path / "image.png"
    save_image(image, "red")

    app = QApplication.instance() or QApplication([])
    window = MainWindow(image)
    window.show()
    app.processEvents()

    assert window.image_view.fit_mode is True
    QTest.keyClick(window.image_view.viewport(), Qt.Key.Key_Space)
    assert window.image_view.fit_mode is False

    QTest.keyClick(window.image_view.viewport(), Qt.Key.Key_Return)
    assert window.isFullScreen()
    QTest.keyClick(window.image_view.viewport(), Qt.Key.Key_Enter)
    assert not window.isFullScreen()

    window.close()
