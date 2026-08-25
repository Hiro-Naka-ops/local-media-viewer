from pathlib import Path

from PIL import Image
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication, QMainWindow

import local_media_viewer.app as app_module
from local_media_viewer.settings import ViewerSettings


def test_associated_file_overrides_last_viewed_file(tmp_path: Path, monkeypatch) -> None:
    last_path = tmp_path / "last.png"
    associated_path = tmp_path / "double-clicked.png"
    Image.new("RGB", (10, 8), "red").save(last_path)
    Image.new("RGB", (12, 9), "blue").save(associated_path)
    saved: list[ViewerSettings] = []
    monkeypatch.setattr(
        app_module,
        "load_settings",
        lambda: ViewerSettings(last_path=str(last_path)),
    )
    monkeypatch.setattr(app_module, "save_settings", saved.append)
    app = QApplication.instance() or QApplication([])
    window = app_module.MainWindow(associated_path)
    try:
        assert window.files[window.index] == associated_path
        assert saved == []
        app.processEvents()
    finally:
        window.close()


def test_saved_window_size_is_restored_during_startup(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    source = QMainWindow()
    source.resize(700, 500)
    encoded = bytes(source.saveGeometry().toBase64()).decode("ascii")
    monkeypatch.setattr(
        app_module,
        "load_settings",
        lambda: ViewerSettings(window_geometry=encoded),
    )
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    window = app_module.MainWindow()
    try:
        assert window.size().width() == 700
        assert window.size().height() == 500
        assert QByteArray.fromBase64(encoded.encode("ascii")) == source.saveGeometry()
        app.processEvents()
    finally:
        window.close()
