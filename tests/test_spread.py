from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.settings import ViewerSettings
from local_media_viewer.spread import compose_spread
from local_media_viewer.viewer import wheel_direction

PAGE_COLORS = ["red", "green", "blue", "orange", "purple", "teal"]


def save_pages(folder: Path, count: int = 6) -> None:
    for number in range(count):
        # Alternating heights exercise the height matching.
        height = 30 if number % 2 == 0 else 26
        Image.new("RGB", (20, height), PAGE_COLORS[number % len(PAGE_COLORS)]).save(
            folder / f"{number}.png"
        )


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def tilt_event(widget, dx: int) -> QWheelEvent:
    spot = QPoint(10, 10)
    return QWheelEvent(
        QPointF(spot),
        widget.mapToGlobal(spot),
        QPoint(dx, 0),
        QPoint(dx, 0),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_compose_spread_matches_heights_and_leaves_no_seam() -> None:
    first = Image.new("RGB", (20, 30), "red")
    second = Image.new("RGB", (20, 15), "blue")

    joined = compose_spread(first, second, right_to_left=False)

    # The short page is scaled up to the tall one, so neither is padded.
    assert joined.height == 30
    assert joined.width == 20 + 40
    middle = joined.height // 2
    # Pixels either side of the join belong to the two pages, with nothing between.
    assert joined.getpixel((19, middle))[:3] == (255, 0, 0)
    assert joined.getpixel((20, middle))[:3] == (0, 0, 255)


def test_right_to_left_puts_the_first_page_on_the_right() -> None:
    first = Image.new("RGB", (20, 20), "red")
    second = Image.new("RGB", (20, 20), "blue")

    rtl = compose_spread(first, second, right_to_left=True)
    ltr = compose_spread(first, second, right_to_left=False)

    assert rtl.getpixel((5, 10))[:3] == (0, 0, 255)
    assert rtl.getpixel((35, 10))[:3] == (255, 0, 0)
    assert ltr.getpixel((5, 10))[:3] == (255, 0, 0)
    assert ltr.getpixel((35, 10))[:3] == (0, 0, 255)


def test_spread_starts_at_the_page_it_was_switched_on_at(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "見開き"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        assert window.displayed_pages == [1]

        window.spread_action.setChecked(True)
        # Switching it on at page 1 pairs 1 with 2, not 0 with 1.
        assert window.spread_anchor == 1
        assert window.displayed_pages == [1, 2]

        # And the pairing keeps that offset while stepping.
        window.navigate(1)
        assert window.displayed_pages == [3, 4]
    finally:
        window.close()


def test_a_spread_turns_two_pages_at_a_time(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "送り"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.spread_action.setChecked(True)
        assert window.displayed_pages == [0, 1]

        window.navigate(1)
        assert window.displayed_pages == [2, 3]
        window.navigate(1)
        assert window.displayed_pages == [4, 5]
        window.navigate(-1)
        assert window.displayed_pages == [2, 3]

        # Turning it off goes back to one page per step.
        window.spread_action.setChecked(False)
        assert window.displayed_pages == [2]
        window.navigate(1)
        assert window.displayed_pages == [3]
    finally:
        window.close()


def test_an_odd_last_page_is_shown_on_its_own(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "端数"
    folder.mkdir()
    save_pages(folder, count=3)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.spread_action.setChecked(True)
        window.navigate(1)
        assert window.displayed_pages == [2]
        assert window.image_view.source_pixmap.width() == 20
    finally:
        window.close()


def test_spread_composes_both_pages_into_one_view(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "合成"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        single = window.image_view.source_pixmap.width()
        window.spread_action.setChecked(True)
        joined = window.image_view.source_pixmap
        # Page 1 is shorter, so it widens when scaled to page 0's height.
        assert joined.width() > single * 2 - 1
        assert joined.height() == 30
    finally:
        window.close()


def test_wheel_tilt_turns_the_page(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "チルト"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "2.png")
        view = window.image_view

        view.wheelEvent(tilt_event(view, 120))
        assert window.displayed_pages == [3]
        view.wheelEvent(tilt_event(view, -120))
        assert window.displayed_pages == [2]
    finally:
        window.close()


def test_wheel_direction_prefers_the_roll_over_the_tilt() -> None:
    class Angles:
        def __init__(self, x, y):
            self._x, self._y = x, y

        def x(self):
            return self._x

        def y(self):
            return self._y

    class Event:
        def __init__(self, x, y):
            self._angles = Angles(x, y)
            self._pixels = Angles(0, 0)

        def angleDelta(self):
            return self._angles

        def pixelDelta(self):
            return self._pixels

    assert wheel_direction(Event(0, -120)) == 1
    assert wheel_direction(Event(0, 120)) == -1
    assert wheel_direction(Event(120, 0)) == 1
    assert wheel_direction(Event(-120, 0)) == -1
    # A mouse reporting both at once still follows the roll.
    assert wheel_direction(Event(-120, 120)) == -1


def test_the_pan_reset_option_returns_to_the_top_of_the_next_page(
    tmp_path: Path, monkeypatch
) -> None:
    folder = tmp_path / "パン"
    folder.mkdir()
    for number in range(3):
        Image.new("RGB", (400, 900), PAGE_COLORS[number]).save(folder / f"{number}.png")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.resize(300, 300)
        window.show()
        app.processEvents()
        window.open_path(folder / "0.png")
        window.image_view.original_size()
        app.processEvents()
        bar = window.image_view.verticalScrollBar()
        assert bar.maximum() > 0

        window.reset_pan_action.setChecked(False)
        bar.setValue(bar.maximum())
        window.navigate(1)
        assert window.image_view.verticalScrollBar().value() == bar.maximum()

        window.reset_pan_action.setChecked(True)
        bar = window.image_view.verticalScrollBar()
        bar.setValue(bar.maximum())
        window.navigate(1)
        assert window.image_view.verticalScrollBar().value() == 0
    finally:
        window.close()


def test_options_appear_under_the_favorites_behind_a_separator(
    tmp_path: Path, monkeypatch
) -> None:
    window = make_window(monkeypatch)
    try:
        menu = window.favorites_menu
        labels = [action.text() for action in menu.actions() if action.text()]
        for option in window.option_actions:
            assert option.text() in labels

        # Exactly one rule divides the favorites from the settings below them.
        actions = menu.actions()
        separators = [i for i, action in enumerate(actions) if action.isSeparator()]
        assert len(separators) == 1
        after = [a.text() for a in actions[separators[0] + 1 :]]
        assert after == [option.text() for option in window.option_actions]
    finally:
        window.close()


def test_options_survive_a_settings_round_trip(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "保存"
    folder.mkdir()
    save_pages(folder)
    stored: list[ViewerSettings] = []

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", stored.append)
    window = app_module.MainWindow()
    try:
        window.open_path(folder / "1.png")
        window.reset_pan_action.setChecked(True)
        window.spread_action.setChecked(True)
        window.spread_rtl_action.setChecked(False)
    finally:
        window.close()

    saved = stored[-1]
    assert saved.reset_pan_on_change is True
    assert saved.spread_view is True
    assert saved.spread_rtl is False
    assert saved.spread_anchor == 1

    monkeypatch.setattr(app_module, "load_settings", lambda: saved)
    restored = app_module.MainWindow()
    try:
        assert restored.reset_pan_action.isChecked() is True
        assert restored.spread_action.isChecked() is True
        assert restored.spread_rtl_action.isChecked() is False
        assert restored.spread_anchor == 1
    finally:
        restored.close()


def test_pages_that_cannot_pair_stay_reachable(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "混在"
    folder.mkdir()
    Image.new("RGB", (20, 30), "red").save(folder / "0.png")
    frames = [Image.new("RGB", (20, 30), tint) for tint in ("green", "blue")]
    frames[0].save(
        folder / "1.gif", save_all=True, append_images=frames[1:], duration=100, loop=0
    )
    Image.new("RGB", (20, 30), "orange").save(folder / "2.png")
    Image.new("RGB", (20, 30), "purple").save(folder / "3.png")

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.spread_action.setChecked(True)

        # An animated partner cannot be joined, so neither page is swallowed by
        # a half-empty pair: both are still walked through one at a time.
        seen = []
        for _ in range(3):
            seen.append([window.files[page].name for page in window.displayed_pages])
            window.navigate(1)
        assert seen == [["0.png"], ["1.gif"], ["2.png", "3.png"]]

        window.navigate(-1)
        assert [window.files[p].name for p in window.displayed_pages] == ["1.gif"]
    finally:
        window.close()


def test_a_video_is_never_paired_into_a_spread(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "動画混在"
    folder.mkdir()
    Image.new("RGB", (20, 30), "red").save(folder / "0.png")
    (folder / "1.mp4").write_bytes(b"not a real video")
    Image.new("RGB", (20, 30), "blue").save(folder / "2.png")
    Image.new("RGB", (20, 30), "teal").save(folder / "3.png")

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.spread_action.setChecked(True)
        assert window.spreadable(1) is False
        assert [window.files[p].name for p in window.displayed_pages] == ["0.png"]

        window.navigate(1)
        assert [window.files[p].name for p in window.displayed_pages] == ["1.mp4"]
        window.navigate(1)
        assert [window.files[p].name for p in window.displayed_pages] == ["2.png", "3.png"]
    finally:
        window.close()


def test_wheel_direction_reads_pixel_deltas_and_ignores_empty_events() -> None:
    class Point:
        def __init__(self, x, y):
            self._x, self._y = x, y

        def x(self):
            return self._x

        def y(self):
            return self._y

    class Event:
        def __init__(self, angle, pixel):
            self._angle, self._pixel = Point(*angle), Point(*pixel)

        def angleDelta(self):
            return self._angle

        def pixelDelta(self):
            return self._pixel

    # Devices that report pixelDelta only must still turn the page...
    assert wheel_direction(Event((0, 0), (40, 0))) == 1
    assert wheel_direction(Event((0, 0), (-40, 0))) == -1
    assert wheel_direction(Event((0, 0), (0, -40))) == 1
    # ...and an event carrying no usable delta must not turn it at all.
    assert wheel_direction(Event((0, 0), (0, 0))) == 0


def test_the_side_buttons_turn_pages(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "サイドボタン"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "2.png")
        steps = []
        window.image_view.navigate.connect(steps.append)

        viewport = window.image_view.viewport()
        for button in (Qt.MouseButton.ForwardButton, Qt.MouseButton.BackButton):
            spot = QPoint(10, 10)
            QApplication.sendEvent(
                viewport,
                QMouseEvent(
                    QMouseEvent.Type.MouseButtonPress,
                    QPointF(spot),
                    viewport.mapToGlobal(spot),
                    button,
                    button,
                    Qt.KeyboardModifier.NoModifier,
                ),
            )
        assert steps == [1, -1]
        assert window.displayed_pages == [2]
    finally:
        window.close()
