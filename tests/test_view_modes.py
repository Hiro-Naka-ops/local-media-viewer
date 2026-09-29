from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.preloader import load_frame
from local_media_viewer.settings import ViewerSettings
from local_media_viewer.viewer import FIT_HEIGHT, FIT_WIDTH, FIT_WINDOW


def make_window(monkeypatch, settings: ViewerSettings | None = None) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    saved: list[ViewerSettings] = []
    monkeypatch.setattr(app_module, "load_settings", lambda: settings or ViewerSettings())
    monkeypatch.setattr(app_module, "save_settings", saved.append)
    window = app_module.MainWindow()
    window.saved = saved
    return window


def save_pages(folder: Path, count: int, size: tuple[int, int] = (40, 30)) -> None:
    for number in range(count):
        Image.new("RGB", size, "red").save(folder / f"{number:02d}.png")


def shown_size(window) -> tuple[int, int]:
    """On-screen size: the pixmap shown, times whatever scale the view adds."""
    view = window.image_view
    pixmap = view.item.pixmap()
    scale = view.transform().m11()
    return round(pixmap.width() * scale), round(pixmap.height() * scale)


def test_fitting_to_width_or_height_fills_that_side(tmp_path: Path, monkeypatch) -> None:
    Image.new("RGB", (300, 1500), "red").save(tmp_path / "tall.png")
    Image.new("RGB", (1500, 300), "blue").save(tmp_path / "wide.png")
    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.resize(900, 700)
        window.show()
        window.open_path(tmp_path / "tall.png")
        app.processEvents()
        view = window.image_view

        window.size_actions[FIT_WIDTH].trigger()
        app.processEvents()
        width, height = shown_size(window)
        # Across the whole view, bar and all; only the vertical bar appears.
        assert width == view.viewport().width()
        # Flush with the left edge, not shifted by half a scroll bar.
        assert view.mapFromScene(0, 0).x() == 0
        assert height > view.viewport().height()
        assert view.verticalScrollBar().maximum() > 0
        assert view.horizontalScrollBar().maximum() == 0

        window.open_path(tmp_path / "wide.png")
        window.size_actions[FIT_HEIGHT].trigger()
        app.processEvents()
        width, height = shown_size(window)
        assert height == view.viewport().height()
        assert view.mapFromScene(0, 0).y() == 0
        assert view.verticalScrollBar().maximum() == 0

        window.size_actions[FIT_WINDOW].trigger()
        app.processEvents()
        width, height = shown_size(window)
        assert width <= view.viewport().width() and height <= view.viewport().height()
    finally:
        window.close()


def test_space_toggles_between_the_chosen_fit_and_actual_size(tmp_path: Path, monkeypatch) -> None:
    Image.new("RGB", (300, 1500), "red").save(tmp_path / "tall.png")
    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.resize(900, 700)
        window.show()
        window.open_path(tmp_path / "tall.png")
        window.size_actions[FIT_WIDTH].trigger()
        app.processEvents()

        window.fit_action.trigger()
        assert window.image_view.display_scale == 1.0
        window.show_size_state()
        assert window.size_actions[app_module.ACTUAL_SIZE].isChecked()

        # Back to the fit that was chosen, not always the whole window.
        window.fit_action.trigger()
        window.show_size_state()
        assert window.image_view.fit_kind == FIT_WIDTH
        assert window.size_actions[FIT_WIDTH].isChecked()
    finally:
        window.close()


def test_the_chosen_fit_is_remembered(tmp_path: Path, monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        window.size_actions[FIT_HEIGHT].trigger()
        assert window.saved[-1].fit_kind == FIT_HEIGHT
    finally:
        window.close()
    restored = make_window(monkeypatch, ViewerSettings(fit_kind=FIT_HEIGHT))
    try:
        assert restored.image_view.fit_kind == FIT_HEIGHT
    finally:
        restored.close()


def test_home_end_and_go_to_page(tmp_path: Path, monkeypatch) -> None:
    save_pages(tmp_path, 10)
    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.show()
        window.open_path(tmp_path / "04.png")
        app.processEvents()
        target = window.image_view.viewport()

        QTest.keyClick(target, Qt.Key.Key_End)
        assert window.index == 9
        QTest.keyClick(target, Qt.Key.Key_Home)
        assert window.index == 0

        asked: list[tuple] = []

        def answer(*args):
            asked.append(args)
            return 7, True

        monkeypatch.setattr(app_module.QInputDialog, "getInt", answer)
        window.go_to_page_action.trigger()
        # Offered from the current page, within 1..count, and taken as a page number.
        assert asked[-1][3:] == (1, 1, 10)
        assert window.index == 6
    finally:
        window.close()


def test_keys_still_work_in_full_screen(tmp_path: Path, monkeypatch) -> None:
    save_pages(tmp_path, 5)
    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.show()
        window.open_path(tmp_path / "00.png")
        window.toggle_fullscreen()
        app.processEvents()
        # The bars that used to carry these keys are hidden in full screen.
        assert not window.menuBar().isVisible() and not window.toolbar.isVisible()
        target = window.image_view.viewport()

        QTest.keyClick(target, Qt.Key.Key_Right)
        assert window.index == 1
        QTest.keyClick(target, Qt.Key.Key_End)
        assert window.index == 4
        QTest.keyClick(target, Qt.Key.Key_Left)
        assert window.index == 3
        fitted = window.image_view.fit_mode
        QTest.keyClick(target, Qt.Key.Key_Space)
        assert window.image_view.fit_mode != fitted
    finally:
        window.close()


def test_a_phone_photo_is_shown_upright_by_both_routes(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    # Stored landscape and tagged "turn 90°": upright it is 100 wide, 200 tall.
    photo = Image.new("RGB", (200, 100), "red")
    exif = photo.getexif()
    exif[0x0112] = 6
    photo.save(tmp_path / "phone.jpg", exif=exif)

    plain = load_frame(tmp_path / "phone.jpg", plain=True)
    assert (plain.qimage.width(), plain.qimage.height()) == (100, 200)
    filtered = load_frame(tmp_path / "phone.jpg", plain=False)
    assert filtered.image.size == (100, 200)
    plain.close()
    filtered.close()


def test_an_animation_keeps_all_its_frames(tmp_path: Path) -> None:
    frames = [Image.new("RGB", (20, 10), color) for color in ("red", "blue", "green")]
    frames[0].save(tmp_path / "anim.gif", save_all=True, append_images=frames[1:], duration=50)
    frame = load_frame(tmp_path / "anim.gif", plain=False)
    # Orientation handling must not flatten it to a single frame.
    assert frame.image.n_frames == 3
    frame.close()
