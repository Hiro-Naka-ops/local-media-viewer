from pathlib import Path
from time import monotonic

from PIL import Image, ImageChops, ImageDraw
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer import enhance as enhance_module
from local_media_viewer.enhance import enhance, upscale_factor
from local_media_viewer.settings import ViewerSettings


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def wait_for(condition, seconds: float = 10.0) -> None:
    app = QApplication.instance()
    deadline = monotonic() + seconds
    while not condition():
        assert monotonic() < deadline, "timed out"
        app.processEvents()


def blocky_picture() -> Image.Image:
    """8x8 blocks a few levels apart, like an over-compressed JPEG, and one thin line."""
    image = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(image)
    for row in range(8):
        for column in range(8):
            level = 120 + 4 * ((row + column) % 2)
            draw.rectangle(
                (column * 8, row * 8, column * 8 + 7, row * 8 + 7), fill=(level,) * 3
            )
    draw.line((0, 40, 63, 40), fill=(0, 0, 0))
    return image


def block_steps(image: Image.Image, scale: int) -> int:
    """Largest jump between horizontal neighbours across the block borders, above the line."""
    grey = image.convert("L")
    jumps = []
    for border in range(8, 64, 8):
        x = border * scale
        for y in range(4 * scale, 32 * scale):
            jumps.append(abs(grey.getpixel((x, y)) - grey.getpixel((x - 1, y))))
    return max(jumps)


def test_enhance_doubles_the_size_and_smooths_block_steps() -> None:
    source = blocky_picture()
    plain = source.resize((128, 128), Image.Resampling.NEAREST)

    result = enhance(source)

    assert result.size == (128, 128)
    assert block_steps(result, 2) < block_steps(plain, 2)
    # The one-pixel line survives unbroken: every column across it still has a dark pixel.
    grey = result.convert("L")
    for x in range(4, 124):
        assert min(grey.getpixel((x, y)) for y in range(76, 86)) < 60


def test_enhance_keeps_transparency() -> None:
    source = Image.new("RGBA", (20, 10), (255, 0, 0, 0))
    source.paste((255, 0, 0, 255), (0, 0, 10, 10))

    result = enhance(source)

    assert result.mode == "RGBA"
    assert result.size == (40, 20)
    assert result.getpixel((5, 10))[3] == 255
    assert result.getpixel((35, 10))[3] == 0


def test_large_pictures_are_cleaned_but_not_enlarged_past_the_limit() -> None:
    limit = enhance_module.LONGEST_SIDE
    assert upscale_factor((limit, 100)) == 1.0
    assert upscale_factor((limit // 4, 100)) == 2.0
    assert upscale_factor((limit * 3 // 4, 100)) * (limit * 3 // 4) == limit


def test_the_button_enhances_only_the_current_picture(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "book"
    folder.mkdir()
    blocky_picture().save(folder / "1.png")
    blocky_picture().save(folder / "2.png")

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        assert window.enhance_action.isEnabled()
        assert window.image_view.source_pixmap.width() == 64

        window.enhance_action.trigger()
        wait_for(lambda: window.image_view.source_pixmap.width() == 128)
        assert window.enhance_action.isChecked()

        # The next page opens as it is, and the button is off for it.
        window.navigate(1)
        assert not window.enhance_action.isChecked()
        assert window.image_view.source_pixmap.width() == 64

        # Pressing again goes back to the file itself.
        window.navigate(-1)
        window.enhance_action.trigger()
        wait_for(lambda: window.image_view.source_pixmap.width() == 128)
        window.enhance_action.trigger()
        assert not window.enhance_action.isChecked()
        assert window.image_view.source_pixmap.width() == 64
    finally:
        window.close()


def test_a_result_for_a_page_left_behind_is_dropped(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "book"
    folder.mkdir()
    blocky_picture().save(folder / "1.png")
    Image.new("RGB", (30, 30), "white").save(folder / "2.png")

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        window.enhance_action.trigger()
        window.navigate(1)
        # Let the worker finish the first page and report back.
        window.enhancer._executor.submit(lambda: None).result()
        QApplication.instance().processEvents()

        assert window.files[window.index].name == "2.png"
        assert window.image_view.source_pixmap.width() == 30
        # The file on disk is never touched.
        assert ImageChops.difference(
            Image.open(folder / "1.png").convert("RGB"), blocky_picture()
        ).getbbox() is None
    finally:
        window.close()


def test_spreads_cannot_be_enhanced(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "book"
    folder.mkdir()
    for name in ("1.png", "2.png", "3.png"):
        Image.new("RGB", (20, 30), "white").save(folder / name)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "2.png")
        window.spread_action.setChecked(True)
        assert len(window.displayed_pages) == 2
        assert not window.enhance_action.isEnabled()
    finally:
        window.close()
