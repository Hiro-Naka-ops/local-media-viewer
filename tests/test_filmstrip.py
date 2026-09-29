from pathlib import Path

from PySide6.QtWidgets import QApplication

from local_media_viewer.filmstrip import GRID_SIZE, LOOKAHEAD, Filmstrip, ThumbnailLoader


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


def fully_shown(filmstrip: Filmstrip, row: int) -> bool:
    rect = filmstrip.view.visualRect(filmstrip.model.index(row, 0))
    return rect.left() >= 0 and rect.right() < filmstrip.view.viewport().width()


def test_paging_keeps_the_next_few_thumbnails_in_view() -> None:
    app = QApplication.instance() or QApplication([])
    filmstrip = Filmstrip()
    # Room for about ten thumbnails in a folder of forty.
    filmstrip.resize(GRID_SIZE.width() * 10, 112)
    count = 40
    filmstrip.set_files([Path(f"image-{index}.png") for index in range(count)])
    filmstrip.show()
    app.processEvents()
    try:
        forward = list(range(count))
        for row in forward + forward[::-1]:
            filmstrip.set_current(row)
            # Both ways, so right-to-left spreads (paging backwards) see ahead too.
            for near in range(max(0, row - LOOKAHEAD), min(count, row + LOOKAHEAD + 1)):
                assert fully_shown(filmstrip, near), (row, near)

        # Moving within the margin leaves the strip where it is. Jumping to 20
        # parks it at the forward margin, so a step back has room to spare.
        filmstrip.set_current(20)
        before = filmstrip.view.horizontalScrollBar().value()
        filmstrip.set_current(19)
        assert filmstrip.view.horizontalScrollBar().value() == before
    finally:
        filmstrip.close()


def test_a_narrow_strip_still_shows_the_current_thumbnail() -> None:
    app = QApplication.instance() or QApplication([])
    filmstrip = Filmstrip()
    # Too narrow for three either side: the current one must still be whole.
    filmstrip.resize(GRID_SIZE.width() * 3, 112)
    filmstrip.set_files([Path(f"image-{index}.png") for index in range(20)])
    filmstrip.show()
    app.processEvents()
    try:
        for row in range(20):
            filmstrip.set_current(row)
            assert fully_shown(filmstrip, row), row
    finally:
        filmstrip.close()


def test_closing_a_strip_while_thumbnails_load_does_not_crash() -> None:
    import gc

    app = QApplication.instance() or QApplication([])
    # Closing used to let the strip be destroyed with a worker still decoding,
    # which killed the process within a few dozen rounds (a segmentation fault
    # on the Mac CI, an access violation on Windows).
    for _ in range(60):
        filmstrip = Filmstrip()
        filmstrip.resize(320, 112)
        filmstrip.show()
        filmstrip.set_files([Path(f"image-{index}.png") for index in range(400)])
        filmstrip.request_visible_thumbnails()
        filmstrip.close()
        del filmstrip
        gc.collect()
        app.processEvents()
