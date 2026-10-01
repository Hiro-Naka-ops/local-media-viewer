from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.settings import ViewerSettings

# Four differently coloured quarters, so every turn and flip looks different.
QUARTERS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
T = Image.Transpose


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def picture() -> Image.Image:
    image = Image.new("RGB", (40, 20))
    for number, colour in enumerate(QUARTERS):
        left, top = (number % 2) * 20, (number // 2) * 10
        image.paste(colour, (left, top, left + 20, top + 10))
    return image


def make_book(folder: Path) -> None:
    folder.mkdir()
    for number in (1, 2):
        picture().save(folder / f"{number}.png")


def shown_size(window: app_module.MainWindow) -> tuple[int, int]:
    pixmap = window.image_view.source_pixmap
    return pixmap.width(), pixmap.height()


def corners(image) -> list[tuple[int, int, int]]:
    """Colours a little in from each corner, of a Pillow image or a QPixmap."""
    if isinstance(image, Image.Image):
        width, height = image.size
        pixel = image.getpixel
    else:
        width, height = image.width(), image.height()
        qimage = image.toImage()

        def pixel(point):
            colour = qimage.pixelColor(*point)
            return (colour.red(), colour.green(), colour.blue())

    points = [(2, 2), (width - 3, 2), (2, height - 3), (width - 3, height - 3)]
    return [tuple(pixel(point)[:3]) for point in points]


@pytest.mark.parametrize(
    ("presses", "expected"),
    [
        (["rotate_right"], [T.ROTATE_270]),
        (["rotate_left"], [T.ROTATE_90]),
        (["rotate_half"], [T.ROTATE_180]),
        (["flip_horizontal"], [T.FLIP_LEFT_RIGHT]),
        (["flip_vertical"], [T.FLIP_TOP_BOTTOM]),
        # Mixed: each press acts on what is on screen at the time.
        (["rotate_right", "flip_horizontal"], [T.ROTATE_270, T.FLIP_LEFT_RIGHT]),
        (["rotate_right", "flip_vertical"], [T.ROTATE_270, T.FLIP_TOP_BOTTOM]),
        (["flip_horizontal", "rotate_right"], [T.FLIP_LEFT_RIGHT, T.ROTATE_270]),
        (["flip_vertical", "rotate_left", "flip_horizontal"],
         [T.FLIP_TOP_BOTTOM, T.ROTATE_90, T.FLIP_LEFT_RIGHT]),
        (["flip_horizontal", "flip_vertical"], [T.ROTATE_180]),
        (["flip_horizontal", "flip_horizontal"], []),
        (["rotate_half", "rotate_half"], []),
    ],
)
def test_turns_and_flips_match_pillow(
    tmp_path: Path, monkeypatch, presses: list[str], expected: list[T]
) -> None:
    folder = tmp_path / "book"
    make_book(folder)
    before = (folder / "1.png").read_bytes()
    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        for press in presses:
            getattr(window, f"{press}_action").trigger()
        wanted = picture()
        for step in expected:
            wanted = wanted.transpose(step)
        assert shown_size(window) == wanted.size
        assert corners(window.image_view.source_pixmap) == corners(wanted)
        assert (folder / "1.png").read_bytes() == before
    finally:
        window.close()


def test_turns_reset_on_the_next_page(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "book"
    make_book(folder)
    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        window.rotate_right_action.trigger()
        window.flip_horizontal_action.trigger()
        window.navigate(1)
        assert corners(window.image_view.source_pixmap) == corners(picture())
        window.navigate(-1)
        assert corners(window.image_view.source_pixmap) == corners(picture())
    finally:
        window.close()


def test_turns_survive_a_redraw_of_the_same_page(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "book"
    make_book(folder)
    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        window.rotate_right_action.trigger()
        # Switching a filter on reloads the page through Pillow (show_current).
        window.brightness.setValue(3)
        assert shown_size(window) == (20, 40)
    finally:
        window.close()


def test_rotation_keys_work_in_full_screen(monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        assert window.rotate_right_action in window.actions()
        assert window.rotate_left_action in window.actions()
    finally:
        window.close()
