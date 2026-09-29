from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.settings import ViewerSettings
from local_media_viewer.viewer import FIT_WIDTH


def make_window(monkeypatch, settings: ViewerSettings | None = None) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    saved: list[ViewerSettings] = []
    monkeypatch.setattr(app_module, "load_settings", lambda: settings or ViewerSettings())
    monkeypatch.setattr(app_module, "save_settings", saved.append)
    window = app_module.MainWindow()
    window.saved = saved
    return window


def bars(window):
    view = window.image_view
    return view.horizontalScrollBar(), view.verticalScrollBar()


def fraction(bar) -> float:
    return (bar.value() - bar.minimum()) / (bar.maximum() - bar.minimum())


def test_every_page_opens_at_the_fixed_spot(tmp_path: Path, monkeypatch) -> None:
    # Pages of different sizes: the spot is kept as a proportion, not in pixels.
    for number, size in enumerate([(900, 1200), (1200, 1600), (800, 1000)]):
        Image.new("RGB", size, "red").save(tmp_path / f"{number}.png")
    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.resize(400, 400)
        window.show()
        window.open_path(tmp_path / "0.png")
        window.image_view.original_size()
        app.processEvents()

        horizontal, vertical = bars(window)
        horizontal.setValue(horizontal.maximum())  # right edge
        vertical.setValue(vertical.maximum() // 3)  # a third of the way down
        window.fix_pan_action.trigger()
        assert window.pan_mode() == app_module.PAN_FIXED

        for _ in range(2):
            # Wherever the reader drags to, the next page opens at the spot.
            horizontal, vertical = bars(window)
            horizontal.setValue(0)
            vertical.setValue(vertical.maximum())
            window.navigate(1)
            app.processEvents()
            horizontal, vertical = bars(window)
            assert fraction(horizontal) == 1.0
            assert abs(fraction(vertical) - 1 / 3) < 0.01
    finally:
        window.close()


def test_fixing_keeps_the_side_that_cannot_scroll(tmp_path: Path, monkeypatch) -> None:
    Image.new("RGB", (300, 1500), "red").save(tmp_path / "tall.png")
    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch, ViewerSettings(pan_x=0.9, pan_y=0.0))
    try:
        window.resize(600, 400)
        window.show()
        window.open_path(tmp_path / "tall.png")
        window.size_actions[FIT_WIDTH].trigger()
        app.processEvents()
        _horizontal, vertical = bars(window)
        vertical.setValue(vertical.maximum() // 2)

        window.fix_pan_action.trigger()
        # Fitted to width, only the height scrolls: the stored width is kept.
        assert window.fixed_pan[0] == 0.9
        assert abs(window.fixed_pan[1] - 0.5) < 0.01
    finally:
        window.close()


def test_the_fixed_spot_is_saved_and_restored(tmp_path: Path, monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        window.fixed_pan = (0.25, 0.75)
        window.choose_pan_mode(app_module.PAN_FIXED)
        saved = window.saved[-1]
        assert (saved.pan_mode, saved.pan_x, saved.pan_y) == ("fixed", 0.25, 0.75)
        # An older copy of the app, which only knows the checkbox, reads "off".
        assert saved.reset_pan_on_change is False
    finally:
        window.close()
    restored = make_window(monkeypatch, saved)
    try:
        assert restored.pan_mode() == app_module.PAN_FIXED
        assert restored.fixed_pan == (0.25, 0.75)
    finally:
        restored.close()


def test_settings_from_the_old_checkbox_carry_over(monkeypatch) -> None:
    # Written before the modes existed: no pan_mode, only the checkbox.
    checked_off = make_window(monkeypatch, ViewerSettings(reset_pan_on_change=False))
    try:
        assert checked_off.pan_mode() == app_module.PAN_KEEP
    finally:
        checked_off.close()
    checked_on = make_window(monkeypatch, ViewerSettings(reset_pan_on_change=True))
    try:
        assert checked_on.pan_mode() == app_module.PAN_TOP
    finally:
        checked_on.close()
