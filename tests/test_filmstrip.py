from pathlib import Path

from PySide6.QtWidgets import QApplication

from local_media_viewer.filmstrip import Filmstrip, ThumbnailLoader


def test_filmstrip_wheel_scrolls_horizontally() -> None:
    app = QApplication.instance() or QApplication([])
    filmstrip = Filmstrip()
    filmstrip.resize(320, 112)
    filmstrip.set_files([Path(f"image-{index}.png") for index in range(20)])
    filmstrip.show()
    app.processEvents()
    bar = filmstrip.view.horizontalScrollBar()
    assert bar.maximum() > 0

    filmstrip.view.scroll_horizontal(-120)
    assert bar.value() == 120
    filmstrip.view.scroll_horizontal(60)
    assert bar.value() == 60
    filmstrip.close()


def test_a_closed_loader_ignores_late_requests(tmp_path: Path) -> None:
    loader = ThumbnailLoader(workers=1)
    loader.close()
    # A queued scroll can still ask after the window has closed; that must be a
    # quiet no-op rather than "cannot schedule new futures after shutdown".
    loader.request(0, tmp_path / "late.png")
