from pathlib import Path

from PySide6.QtWidgets import QApplication

from local_media_viewer.filmstrip import Filmstrip


def test_filmstrip_wheel_scrolls_horizontally() -> None:
    app = QApplication.instance() or QApplication([])
    filmstrip = Filmstrip()
    filmstrip.resize(320, 112)
    filmstrip.set_files([Path(f"image-{index}.png") for index in range(20)])
    filmstrip.show()
    app.processEvents()
    bar = filmstrip.scroll.horizontalScrollBar()
    assert bar.maximum() > 0

    filmstrip.scroll.scroll_horizontal(-120)
    assert bar.value() == 120
    filmstrip.scroll.scroll_horizontal(60)
    assert bar.value() == 60
    filmstrip.close()
