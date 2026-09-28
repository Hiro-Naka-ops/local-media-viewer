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


def make_window(monkeypatch, **settings) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", lambda: ViewerSettings(**settings))
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

    window = make_window(monkeypatch, spread_cover=False)
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

    window = make_window(monkeypatch, spread_cover=False)
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

    window = make_window(monkeypatch, spread_cover=False)
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


def sections(menu) -> list[list]:
    """A menu's actions, split at its separators."""
    groups: list[list] = [[]]
    for action in menu.actions():
        if action.isSeparator():
            groups.append([])
        else:
            groups[-1].append(action)
    return groups


def test_options_live_in_the_menu_bar(tmp_path: Path, monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        titles = [action.text() for action in window.menuBar().actions()]
        assert titles == [
            "ファイル(&F)", "表示(&V)", "見開き(&S)", "お気に入り(&A)", "ウィンドウ(&W)"
        ]

        panels, drawing, spread = window.option_groups
        view = sections(window.view_menu)
        # Zoom, the panels, how the picture is drawn, and the language closing
        # the menu, each ruled off from the next. Full screen is a window matter.
        assert view == [
            [window.fit_action],
            panels,
            drawing,
            [window.language_menu.menuAction()],
        ]
        # The spread settings have a menu of their own.
        assert sections(window.spread_menu) == [spread]
        assert [a.text() for a in spread] == [
            "見開き表示（2ページ）",
            "見開きを右送りにする",
            "1ページ目を表紙として単独表示",
            "見開きページをずらす",
        ]
        # What is left on the toolbar is only paging (the video controls are
        # hidden until a video is open).
        shown = [a for a in window.toolbar.actions() if a.isVisible()]
        assert shown == [window.previous_action, window.next_action]
    finally:
        window.close()


def test_the_favorites_menu_holds_no_settings(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "お気に入り"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.add_favorite()
        window.prepare_favorites_menu()
        labels = {action.text() for action in window.favorites_menu.actions()}
        # A list of bookmarked folders is not where the display options belong.
        assert labels.isdisjoint({action.text() for action in window.option_actions})
    finally:
        window.close()


def test_a_fresh_install_starts_with_the_pan_reset_on() -> None:
    assert ViewerSettings().reset_pan_on_change is True


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

    window = make_window(monkeypatch, spread_cover=False)
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

    window = make_window(monkeypatch, spread_cover=False)
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


def test_the_pan_reset_centres_on_the_new_image_not_the_previous_one(
    tmp_path: Path, monkeypatch
) -> None:
    folder = tmp_path / "パン幅"
    folder.mkdir()
    # Different widths: centring on a stale scrollbar range would land wrong.
    for number, width in enumerate((1200, 700, 2000)):
        Image.new("RGB", (width, 1600), PAGE_COLORS[number]).save(folder / f"{number}.png")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.resize(400, 360)
        window.show()
        app.processEvents()
        window.reset_pan_action.setChecked(True)
        window.open_path(folder / "0.png")
        window.image_view.original_size()
        app.processEvents()

        for _ in range(2):
            view = window.image_view
            view.horizontalScrollBar().setValue(view.horizontalScrollBar().maximum())
            view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
            window.navigate(1)
            app.processEvents()

            horizontal = window.image_view.horizontalScrollBar()
            vertical = window.image_view.verticalScrollBar()
            assert horizontal.maximum() > 0
            middle = (horizontal.minimum() + horizontal.maximum()) // 2
            assert horizontal.value() == middle
            assert vertical.value() == vertical.minimum()
    finally:
        window.close()


def test_pan_is_left_alone_when_the_option_is_off(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "パン固定"
    folder.mkdir()
    for number in range(2):
        Image.new("RGB", (1200, 1600), PAGE_COLORS[number]).save(folder / f"{number}.png")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.resize(400, 360)
        window.show()
        app.processEvents()
        window.reset_pan_action.setChecked(False)
        window.open_path(folder / "0.png")
        window.image_view.original_size()
        app.processEvents()

        vertical = window.image_view.verticalScrollBar()
        vertical.setValue(vertical.maximum())
        kept = vertical.value()
        assert kept > 0

        window.navigate(1)
        app.processEvents()
        assert window.image_view.verticalScrollBar().value() == kept
    finally:
        window.close()


def test_the_first_page_stands_alone_as_a_cover(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "表紙"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.spread_action.setChecked(True)
        # Page 1 is the cover, so it is shown on its own and the pairs start
        # from the page after it.
        assert window.displayed_pages == [0]
        assert window.image_view.source_pixmap.width() == 20

        window.navigate(1)
        assert window.displayed_pages == [1, 2]
        window.navigate(1)
        assert window.displayed_pages == [3, 4]
        window.navigate(-1)
        assert window.displayed_pages == [1, 2]
        window.navigate(-1)
        assert window.displayed_pages == [0]
    finally:
        window.close()


def test_moving_to_another_folder_re_covers_the_spread(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "1"
    second = tmp_path / "2"
    for folder in (first, second):
        folder.mkdir()
        save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(first / "1.png")
        window.spread_action.setChecked(True)
        assert window.displayed_pages == [1, 2]
        assert window.spread_anchor == 1

        # A different book starts over at its own cover rather than inheriting
        # whatever offset the previous folder was left on.
        window.open_folder(second, 0)
        assert window.displayed_pages == [0]
        window.navigate(1)
        assert window.displayed_pages == [1, 2]
    finally:
        window.close()


def test_an_even_offset_folder_is_re_covered_too(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "1"
    second = tmp_path / "2"
    for folder in (first, second):
        folder.mkdir()
        save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(first / "1.png")
        window.spread_action.setChecked(True)
        window.shift_spread()
        # Shifting leaves this folder on an even offset.
        assert window.spread_anchor == 2
        assert window.displayed_pages == [2, 3]

        window.open_folder(second, 0)
        assert window.spread_anchor == 1
        assert window.displayed_pages == [0]
    finally:
        window.close()


def test_the_cover_option_can_be_turned_off(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "表紙なし"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.spread_action.setChecked(True)
        assert window.displayed_pages == [0]

        window.spread_cover_action.setChecked(False)
        # Without the cover rule the very first two pages pair up again.
        assert window.displayed_pages == [0, 1]
        window.navigate(1)
        assert window.displayed_pages == [2, 3]
    finally:
        window.close()


def test_the_cover_setting_survives_a_round_trip(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "設定"
    folder.mkdir()
    save_pages(folder)
    stored: list[ViewerSettings] = []

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", stored.append)
    window = app_module.MainWindow()
    try:
        window.open_path(folder / "0.png")
        window.spread_cover_action.setChecked(False)
    finally:
        window.close()

    saved = stored[-1]
    assert saved.spread_cover is False

    monkeypatch.setattr(app_module, "load_settings", lambda: saved)
    restored = app_module.MainWindow()
    try:
        assert restored.spread_cover_action.isChecked() is False
    finally:
        restored.close()


def test_a_fresh_install_shows_the_first_page_as_a_cover() -> None:
    assert ViewerSettings().spread_cover is True


def test_a_resumed_folder_keeps_its_saved_pairing(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "再開"
    folder.mkdir()
    save_pages(folder)

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    monkeypatch.setattr(
        app_module,
        "load_settings",
        lambda: ViewerSettings(
            last_path=str(folder / "2.png"), spread_view=True, spread_anchor=2
        ),
    )
    window = app_module.MainWindow()
    try:
        # Restoring is not a move into a new folder, so the offset the user
        # left the book on is kept rather than reset to the cover rule.
        assert window.spread_anchor == 2
        assert window.displayed_pages == [2, 3]
    finally:
        window.close()


def test_shifting_swaps_one_page_out_of_the_pair(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "ずらし"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.spread_action.setChecked(True)
        window.navigate(1)
        assert window.displayed_pages == [1, 2]

        # The far page of the pair stays and becomes the first half of the new
        # one, so exactly one of the two pages on screen is exchanged.
        window.shift_spread()
        assert window.displayed_pages == [2, 3]
        window.shift_spread()
        assert window.displayed_pages == [3, 4]
    finally:
        window.close()


def test_a_shift_holds_for_the_rest_of_the_folder(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "ずらし継続"
    folder.mkdir()
    save_pages(folder, count=8)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.spread_action.setChecked(True)
        window.navigate(1)
        window.shift_spread()
        assert window.displayed_pages == [2, 3]

        # Paging on either side keeps the new offset rather than snapping back.
        window.navigate(1)
        assert window.displayed_pages == [4, 5]
        window.navigate(1)
        assert window.displayed_pages == [6, 7]
        window.navigate(-1)
        assert window.displayed_pages == [4, 5]
        window.navigate(-1)
        assert window.displayed_pages == [2, 3]
    finally:
        window.close()


def test_shifting_on_the_last_page_stops_rather_than_wrapping(
    tmp_path: Path, monkeypatch
) -> None:
    folder = tmp_path / "終端"
    folder.mkdir()
    save_pages(folder, count=4)

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "0.png")
        window.spread_action.setChecked(True)
        window.navigate(1)
        assert window.displayed_pages == [1, 2]
        window.shift_spread()
        assert window.displayed_pages == [2, 3]
        window.shift_spread()
        # The last page has no partner left, so it stands on its own.
        assert window.displayed_pages == [3]
        # And there is nothing further to shift onto.
        window.shift_spread()
        assert window.displayed_pages == [3]
    finally:
        window.close()


def test_shifting_with_the_spread_off_turns_it_on(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "オフから"
    folder.mkdir()
    save_pages(folder)

    window = make_window(monkeypatch, spread_cover=False)
    try:
        window.open_path(folder / "2.png")
        assert window.displayed_pages == [2]
        window.shift_spread()
        assert window.spread_action.isChecked() is True
        assert window.displayed_pages == [2, 3]
    finally:
        window.close()


def test_a_shift_does_not_survive_a_folder_move(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "1"
    second = tmp_path / "2"
    for folder in (first, second):
        folder.mkdir()
        save_pages(folder)

    window = make_window(monkeypatch)
    try:
        window.open_path(first / "0.png")
        window.spread_action.setChecked(True)
        window.navigate(1)
        window.shift_spread()
        assert window.displayed_pages == [2, 3]

        window.open_folder(second, 0)
        assert window.displayed_pages == [0]
        window.navigate(1)
        assert window.displayed_pages == [1, 2]
    finally:
        window.close()


def test_a_file_opened_at_startup_does_not_inherit_another_folders_offset(
    tmp_path: Path, monkeypatch
) -> None:
    previous = tmp_path / "前回"
    opened = tmp_path / "今回"
    for folder in (previous, opened):
        folder.mkdir()
        save_pages(folder)

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    monkeypatch.setattr(
        app_module,
        "load_settings",
        lambda: ViewerSettings(
            last_path=str(previous / "2.png"), spread_view=True, spread_anchor=2
        ),
    )
    # Double-clicking a file in a different folder opens a different book, so
    # the even offset left in the previous one must not pair its cover up.
    window = app_module.MainWindow(opened / "0.png")
    try:
        assert window.current_folder == opened
        assert window.spread_anchor == 1
        assert window.displayed_pages == [0]
        window.navigate(1)
        assert window.displayed_pages == [1, 2]
    finally:
        window.close()
