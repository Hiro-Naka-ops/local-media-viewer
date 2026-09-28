import unicodedata
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.filmstrip import read_thumbnail
from local_media_viewer.media import listed_path, media_files
from local_media_viewer.preloader import load_frame
from local_media_viewer.settings import ViewerSettings


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def save_heic(path: Path, color: str) -> None:
    Image.new("RGB", (40, 30), color).save(path)


def test_iphone_photos_are_listed_and_decoded(tmp_path: Path) -> None:
    save_heic(tmp_path / "IMG_0001.HEIC", "red")
    save_heic(tmp_path / "IMG_0002.heif", "blue")
    files = media_files(tmp_path)
    assert [path.name for path in files] == ["IMG_0001.HEIC", "IMG_0002.heif"]

    # Qt cannot read HEIC on Windows, so the page falls back to Pillow there;
    # on a Mac Qt's own decoder may take it instead. Either way it decodes.
    frame = load_frame(files[0], plain=True)
    if frame.image is not None:
        size = frame.image.size
    else:
        size = (frame.qimage.width(), frame.qimage.height())
    assert size == (40, 30)
    frame.close()

    thumbnail = read_thumbnail(files[1])
    assert not thumbnail.isNull()
    assert thumbnail.pixelColor(5, 5).blue() > 200


def test_a_heic_file_opens_in_the_window(tmp_path: Path, monkeypatch) -> None:
    save_heic(tmp_path / "photo.heic", "green")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "photo.heic")
        assert window.files == [tmp_path / "photo.heic"]
        assert not window.image_view.source_pixmap.isNull()
    finally:
        window.close()


def test_a_decomposed_japanese_name_finds_its_composed_listing(tmp_path: Path) -> None:
    composed = unicodedata.normalize("NFC", "ガイド.png")
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    files = [tmp_path / composed]
    # macOS can hand the file dialog's path back decomposed; it is the same file.
    assert listed_path(files, tmp_path / decomposed) == files[0]
    assert listed_path(files, tmp_path / "別.png") is None
