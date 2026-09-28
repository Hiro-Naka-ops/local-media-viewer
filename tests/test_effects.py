from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.effects import (
    LINE_COLOR,
    MONOCHROME,
    NONE,
    SEPIA,
    apply_effect,
    parse_color,
)
from local_media_viewer.settings import ViewerSettings

BLUE = "#24478F"


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def line_art() -> Image.Image:
    """White paper, a black stroke and a mid grey, as RGBA."""
    image = Image.new("RGBA", (3, 1), (255, 255, 255, 255))
    image.putpixel((1, 0), (0, 0, 0, 255))
    image.putpixel((2, 0), (128, 128, 128, 255))
    return image


def test_no_effect_returns_the_image_untouched() -> None:
    source = line_art()
    assert apply_effect(source, NONE, BLUE) is source


def test_the_line_colour_effect_leaves_white_alone(tmp_path: Path) -> None:
    result = apply_effect(line_art(), LINE_COLOR, BLUE).convert("RGBA")

    # White paper must stay exactly white; only the drawing is recoloured.
    assert result.getpixel((0, 0))[:3] == (255, 255, 255)
    assert result.getpixel((1, 0))[:3] == (0x24, 0x47, 0x8F)
    # A mid grey lands between the two ends rather than flattening.
    grey = result.getpixel((2, 0))[:3]
    assert all(0x24 < channel for channel in grey[:1])
    assert grey != (255, 255, 255) and grey != (0x24, 0x47, 0x8F)


def test_monochrome_keeps_black_and_white_but_drains_colour() -> None:
    source = Image.new("RGBA", (2, 1), (255, 255, 255, 255))
    source.putpixel((1, 0), (200, 40, 40, 255))

    result = apply_effect(source, MONOCHROME, BLUE).convert("RGBA")

    assert result.getpixel((0, 0))[:3] == (255, 255, 255)
    red, green, blue = result.getpixel((1, 0))[:3]
    assert red == green == blue


def test_sepia_tints_the_paper_warm() -> None:
    result = apply_effect(line_art(), SEPIA, BLUE).convert("RGBA")

    paper = result.getpixel((0, 0))[:3]
    assert paper[0] > paper[2]  # warmer than it is cool
    assert paper != (255, 255, 255)


def test_effects_keep_the_alpha_channel() -> None:
    source = Image.new("RGBA", (1, 1), (10, 10, 10, 77))
    for effect in (MONOCHROME, SEPIA, LINE_COLOR):
        assert apply_effect(source, effect, BLUE).getpixel((0, 0))[3] == 77


def test_a_broken_colour_falls_back_instead_of_raising() -> None:
    assert parse_color("#24478F") == (0x24, 0x47, 0x8F)
    assert parse_color("nonsense") == parse_color("#24478F")
    assert parse_color("") == parse_color("#24478F")


def test_the_effect_submenu_sits_with_the_drawing_options(tmp_path: Path, monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        panels = [action.text() for action in window.option_groups[0]]
        assert panels == ["フィルムストリップ", "フィルター"]

        group = window.option_groups[1]
        labels = [action.text() for action in group]
        assert labels == ["エフェクト", "並び順", "パン位置を毎回初期化する"]

        # エフェクト is a folder: clicking it opens a submenu.
        effect_entry = next(a for a in group if a.text() == "エフェクト")
        assert effect_entry.menu() is window.effect_menu

        rows = [a.text() for a in window.effect_menu.actions() if not a.isSeparator()]
        assert rows == ["なし", "モノクロ", "セピア", "線の色を変える", "線の色を選ぶ…"]
    finally:
        window.close()


def test_only_one_effect_is_ever_chosen(tmp_path: Path, monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        assert window.current_effect() == NONE

        for effect in (MONOCHROME, SEPIA, LINE_COLOR, NONE):
            window.choose_effect(effect)
            assert window.current_effect() == effect
            checked = [k for k, a in window.effect_actions.items() if a.isChecked()]
            assert checked == [effect]
    finally:
        window.close()


def test_picking_a_colour_switches_the_effect_on(tmp_path: Path, monkeypatch) -> None:
    class StubColor:
        def __init__(self, name="#aa3311", valid=True):
            self._name, self._valid = name, valid

        def isValid(self):
            return self._valid

        def name(self):
            return self._name

    class StubDialog:
        ColorDialogOption = app_module.QColorDialog.ColorDialogOption
        chosen = StubColor()

        @staticmethod
        def getColor(*_args, **_kwargs):
            return StubDialog.chosen

    window = make_window(monkeypatch)
    monkeypatch.setattr(app_module, "QColorDialog", StubDialog)
    monkeypatch.setattr(app_module, "QColor", lambda *_a, **_k: StubColor())
    try:
        window.choose_line_color()
        assert window.line_color == "#aa3311"
        assert window.current_effect() == LINE_COLOR

        # Cancelling leaves both the colour and the current effect alone.
        window.choose_effect(NONE)
        StubDialog.chosen = StubColor("#000000", valid=False)
        window.choose_line_color()
        assert window.line_color == "#aa3311"
        assert window.current_effect() == NONE
    finally:
        window.close()


def test_the_effect_survives_a_settings_round_trip(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "エフェクト保存"
    folder.mkdir()
    Image.new("RGB", (12, 8), "white").save(folder / "0.png")
    stored: list[ViewerSettings] = []

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", stored.append)
    window = app_module.MainWindow()
    try:
        window.open_path(folder / "0.png")
        window.line_color = "#112233"
        window.choose_effect(SEPIA)
    finally:
        window.close()

    assert stored[-1].effect == SEPIA
    assert stored[-1].line_color == "#112233"

    monkeypatch.setattr(app_module, "load_settings", lambda: stored[-1])
    restored = app_module.MainWindow()
    try:
        assert restored.current_effect() == SEPIA
        assert restored.line_color == "#112233"
        assert restored.effect_actions[SEPIA].isChecked()
    finally:
        restored.close()


def test_the_effect_reaches_the_displayed_image(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "描画"
    folder.mkdir()
    art = Image.new("RGB", (4, 1), "white")
    art.putpixel((1, 0), (0, 0, 0))
    art.save(folder / "0.png")

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.line_color = BLUE
        window.choose_effect(LINE_COLOR)

        shown = window.image_view.source_pixmap.toImage()
        assert shown.pixelColor(0, 0).name() == "#ffffff"
        assert shown.pixelColor(1, 0).name() == BLUE.lower()
    finally:
        window.close()
