"""Guards for the shortcuts that keep opening a folder and turning a page quick.

Each of these is a behaviour that is invisible when it works and only shows up
as the app feeling slow, so it is pinned here rather than left to be noticed.
"""

from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

import local_media_viewer.app as app_module
from local_media_viewer.filmstrip import Filmstrip
from local_media_viewer.settings import ViewerSettings


def save_pages(folder: Path, count: int) -> None:
    for index in range(count):
        Image.new("RGB", (16, 12), "teal").save(folder / f"{index:03d}.png")


def make_window(monkeypatch, saved: list | None = None):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(
        app_module, "save_settings", saved.append if saved is not None else lambda _s: None
    )
    # Paging past either end offers to open the neighbouring folder, and an
    # unanswered modal would hang the run.
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    return app_module.MainWindow()


def test_only_thumbnails_near_the_view_are_requested() -> None:
    QApplication.instance() or QApplication([])
    filmstrip = Filmstrip()
    filmstrip.resize(320, 112)
    filmstrip.show()
    try:
        filmstrip.set_files([Path(f"image-{index}.png") for index in range(400)])
        # Building the strip must not decode anything: the whole folder used to
        # be read here, which is what made opening a large folder stall.
        assert filmstrip.requested == set()
        filmstrip.request_visible_thumbnails()
        assert 0 < len(filmstrip.requested) < 400
    finally:
        filmstrip.close()


def test_selecting_a_page_moves_the_highlight() -> None:
    QApplication.instance() or QApplication([])
    filmstrip = Filmstrip()
    try:
        filmstrip.set_files([Path(f"image-{index}.png") for index in range(10)])
        filmstrip.set_current(3)
        # The view tracks the selection itself, so marking a page costs nothing
        # per file the way restyling every button did.
        assert filmstrip.view.currentIndex().row() == 3
        filmstrip.set_current(4)
        assert filmstrip.view.currentIndex().row() == 4
        assert filmstrip.current == 4
    finally:
        filmstrip.close()


def test_a_large_folder_builds_no_widget_per_file() -> None:
    QApplication.instance() or QApplication([])
    filmstrip = Filmstrip()
    filmstrip.resize(800, 112)
    filmstrip.show()
    try:
        filmstrip.set_files([Path(f"image-{index}.png") for index in range(4000)])
        assert filmstrip.model.rowCount() == 4000
        first, last = filmstrip.visible_range()
        # Only the rows near the viewport are ever realised.
        assert last - first < 60
    finally:
        filmstrip.close()


def test_a_plain_page_skips_pillow(tmp_path: Path, monkeypatch) -> None:
    save_pages(tmp_path, 3)
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "000.png")
        assert window.plain_view() is True
        # No Pillow handle is kept, because the bitmap went from the decoder
        # straight into the view.
        assert window.image is None
        assert not window.image_view.source_pixmap.isNull()
    finally:
        window.close()


def test_a_filter_brings_pillow_back(tmp_path: Path, monkeypatch) -> None:
    save_pages(tmp_path, 3)
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "000.png")
        assert window.image is None
        window.brightness.setValue(30)
        assert window.plain_view() is False
        assert window.image is not None
        assert not window.image_view.source_pixmap.isNull()
    finally:
        window.close()


def test_an_animation_keeps_pillow_even_with_no_filter(tmp_path: Path, monkeypatch) -> None:
    frames = [Image.new("RGB", (16, 12), color) for color in ("red", "green", "blue")]
    frames[0].save(tmp_path / "a.gif", save_all=True, append_images=frames[1:], duration=80)
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "a.gif")
        assert window.plain_view() is True
        assert window.image is not None
        assert int(getattr(window.image, "n_frames", 1)) == 3
    finally:
        window.close()


def test_paging_does_not_write_settings_per_page(tmp_path: Path, monkeypatch) -> None:
    save_pages(tmp_path, 5)
    saved: list = []
    window = make_window(monkeypatch, saved)
    try:
        window.open_path(tmp_path / "000.png")
        saved.clear()
        for _ in range(4):
            window.navigate(1)
        # The write is deferred to a timer, so a burst of page turns does not
        # re-serialise every favourite thumbnail once per page.
        assert saved == []
        assert window.settings_timer.isActive()
        window.persist_settings()
        assert len(saved) == 1
        assert saved[0].last_path == str(tmp_path / "004.png")
    finally:
        window.close()


def test_closing_flushes_a_pending_settings_write(tmp_path: Path, monkeypatch) -> None:
    save_pages(tmp_path, 3)
    saved: list = []
    window = make_window(monkeypatch, saved)
    window.open_path(tmp_path / "000.png")
    saved.clear()
    window.navigate(1)
    assert saved == []
    window.close()
    assert len(saved) == 1
    assert saved[0].last_path == str(tmp_path / "001.png")


def test_the_spread_probe_reads_each_file_once(tmp_path: Path, monkeypatch) -> None:
    save_pages(tmp_path, 4)
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "002.png")
        probed: list = []
        real_is_animated = app_module.is_animated

        # is_animated runs only for an uncached probe, so counting it counts
        # the header reads the pairing does rather than the real decodes.
        def counting_is_animated(image):
            probed.append(image)
            return real_is_animated(image)

        monkeypatch.setattr(app_module, "is_animated", counting_is_animated)
        window.spread_action.setChecked(True)
        assert window.displayed_pages == [2, 3]
        assert len(probed) == 2
        window.navigate(-1)
        assert window.displayed_pages == [0, 1]
        assert len(probed) == 4
        window.navigate(1)
        assert window.displayed_pages == [2, 3]
        # Paging back over a pair must not re-read headers already answered.
        assert len(probed) == 4
    finally:
        window.close()
