from pathlib import Path
from time import monotonic

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer import transition
from local_media_viewer.settings import ViewerSettings


def make_window(monkeypatch, saved: list | None = None) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(
        app_module,
        "save_settings",
        lambda settings: saved.append(settings) if saved is not None else None,
    )
    return app_module.MainWindow()


def make_book(folder: Path, pages: int = 3) -> None:
    folder.mkdir()
    for number in range(pages):
        Image.new("RGB", (20, 20), (number * 40, 0, 0)).save(folder / f"{number}.png")
    # A folder after this one, which paging by hand would ask about.
    (folder.parent / "next").mkdir()
    Image.new("RGB", (20, 20)).save(folder.parent / "next" / "0.png")


def test_slideshow_turns_pages_and_stops_at_the_last(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        assert not window.slideshow_timer.isActive()

        window.slideshow_action.trigger()
        assert window.slideshow_timer.isActive()
        assert window.slideshow_timer.interval() == 5000

        window.slideshow_timer.timeout.emit()
        assert window.index == 1
        # Each page restarts the wait.
        assert window.slideshow_timer.isActive()
        window.slideshow_timer.timeout.emit()
        assert window.index == 2

        # The last page ends it, without asking about the next folder (a
        # question box here would block the test).
        window.slideshow_timer.timeout.emit()
        assert window.index == 2
        assert window.current_folder == tmp_path / "book"
        assert not window.slideshow_action.isChecked()
        assert not window.slideshow_timer.isActive()
    finally:
        window.close()


def test_turning_a_page_by_hand_restarts_the_wait(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        window.slideshow_action.trigger()
        # Pretend most of the wait has passed.
        window.slideshow_timer.start(10)
        window.navigate(1)
        assert window.index == 1
        assert window.slideshow_timer.remainingTime() > 4000
    finally:
        window.close()


def test_stopping_the_slideshow_stops_the_timer(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        window.slideshow_action.trigger()
        window.slideshow_action.trigger()
        assert not window.slideshow_timer.isActive()
        window.navigate(1)
        assert not window.slideshow_timer.isActive()
    finally:
        window.close()


def test_the_page_waits_while_a_menu_or_dialog_is_open(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        window.slideshow_action.trigger()
        monkeypatch.setattr(window, "slideshow_blocked", lambda: True)
        window.slideshow_timer.timeout.emit()
        assert window.index == 0
        assert window.slideshow_timer.isActive()
    finally:
        window.close()


def test_a_video_plays_through_once_before_the_next_page(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        window.slideshow_action.trigger()
        # Stand in for a 9 second video that is 2 seconds in.
        window.stack.setCurrentWidget(window.video_view)
        monkeypatch.setattr(window.player, "duration", lambda: 9000)
        monkeypatch.setattr(window.player, "position", lambda: 2000)

        window.slideshow_timer.timeout.emit()
        assert window.index == 0
        assert window.slideshow_timer.interval() == 7000

        # It loops, so the second time round it moves on regardless.
        window.slideshow_timer.timeout.emit()
        assert window.index == 1
    finally:
        window.close()


def test_the_interval_is_chosen_and_saved_but_running_is_not(
    tmp_path: Path, monkeypatch
) -> None:
    make_book(tmp_path / "book")
    saved: list[ViewerSettings] = []
    window = make_window(monkeypatch, saved)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        window.slideshow_action.trigger()
        window.slideshow_interval_actions[10].trigger()
        assert window.slideshow_timer.interval() == 10000
        assert saved[-1].slideshow_seconds == 10
        # Reopening the app with what was just saved starts nothing by itself.
        monkeypatch.setattr(app_module, "load_settings", lambda: saved[-1])
        reopened = app_module.MainWindow()
        try:
            assert reopened.slideshow_seconds == 10
            assert not reopened.slideshow_action.isChecked()
            assert not reopened.slideshow_timer.isActive()
        finally:
            reopened.close()
    finally:
        window.close()


def test_a_slideshow_never_starts_by_itself_and_has_a_key(monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        assert not window.slideshow_action.isChecked()
        # With nothing open there is nothing to turn.
        window.slideshow_action.trigger()
        assert not window.slideshow_action.isChecked()
        # Held by the window, so F5 works in full screen with the bars hidden.
        assert window.slideshow_action in window.actions()
    finally:
        window.close()


@pytest.mark.parametrize("broken", [0, -3, 99999, "5", 2.5, True])
def test_a_broken_saved_interval_falls_back(monkeypatch, broken) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        app_module, "load_settings", lambda: ViewerSettings(slideshow_seconds=broken)
    )
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    window = app_module.MainWindow()
    try:
        assert window.slideshow_seconds == 5
        assert window.slideshow_interval_actions[5].isChecked()
    finally:
        window.close()


def test_any_number_of_seconds_can_be_picked(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    saved: list[ViewerSettings] = []
    window = make_window(monkeypatch, saved)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        monkeypatch.setattr(app_module.QInputDialog, "getInt", lambda *_args: (7, True))
        window.slideshow_custom_action.trigger()
        assert window.slideshow_seconds == 7
        assert saved[-1].slideshow_seconds == 7
        assert window.slideshow_custom_action.isChecked()
        assert window.slideshow_custom_action.text() == "秒数を指定…（7秒）"

        # Backing out of the dialog leaves the choice, and its tick, alone.
        window.slideshow_interval_actions[3].trigger()
        monkeypatch.setattr(app_module.QInputDialog, "getInt", lambda *_args: (99, False))
        window.slideshow_custom_action.trigger()
        assert window.slideshow_seconds == 3
        assert window.slideshow_interval_actions[3].isChecked()
        assert not window.slideshow_custom_action.isChecked()
    finally:
        window.close()


def colour_at(image, x: int, y: int) -> tuple[int, int, int]:
    colour = image.pixelColor(x, y)
    return (colour.red(), colour.green(), colour.blue())


def frame(kind: str, progress: float) -> QImage:
    """One moment of a change from an all-red view to an all-blue one."""
    QApplication.instance() or QApplication([])
    before, after = QPixmap(100, 60), QPixmap(100, 60)
    before.fill(QColor(255, 0, 0))
    after.fill(QColor(0, 0, 255))
    image = QImage(100, 60, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    transition.paint_transition(painter, kind, progress, before, after, 100, 60)
    painter.end()
    return image


@pytest.mark.parametrize("kind", sorted(transition.TRANSITIONS - {transition.NONE}))
def test_every_change_starts_on_the_old_page_and_ends_on_the_new(kind: str) -> None:
    for point in ((2, 2), (50, 30), (97, 57)):
        assert colour_at(frame(kind, 0.0), *point) == (255, 0, 0)
        assert colour_at(frame(kind, 1.0), *point) == (0, 0, 255)


def test_each_change_looks_like_its_name_half_way() -> None:
    red, blue, black = (255, 0, 0), (0, 0, 255), (0, 0, 0)
    # A plain fade is both pages at once.
    mixed = colour_at(frame(transition.FADE, 0.5), 50, 30)
    assert 100 < mixed[0] < 155 and 100 < mixed[2] < 155
    # Out to black, then in: neither page shows at the middle.
    assert colour_at(frame(transition.FADE_BLACK, 0.5), 50, 30) == black
    # The new page pushes in from the right ...
    slide = frame(transition.SLIDE_LEFT, 0.5)
    assert colour_at(slide, 10, 30) == red and colour_at(slide, 90, 30) == blue
    # ... or up from the bottom.
    rise = frame(transition.SLIDE_UP, 0.5)
    assert colour_at(rise, 50, 5) == red and colour_at(rise, 50, 55) == blue
    # The old page grows as it fades, so the view stays covered to its corners.
    zoom = colour_at(frame(transition.ZOOM, 0.5), 1, 1)
    assert 100 < zoom[0] < 155 and 100 < zoom[2] < 155


def test_the_slideshow_plays_the_chosen_change(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    saved: list[ViewerSettings] = []
    window = make_window(monkeypatch, saved)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        overlay = window.transition_overlay
        window.transition_actions[transition.SLIDE_LEFT].trigger()
        window.transition_speed_actions[1200].trigger()
        assert (saved[-1].slideshow_effect, saved[-1].slideshow_effect_ms) == (
            transition.SLIDE_LEFT,
            1200,
        )

        # Paging by hand stays instant.
        window.navigate(1)
        assert not overlay.running()
        window.navigate(-1)

        window.slideshow_action.trigger()
        window.slideshow_timer.timeout.emit()
        assert window.index == 1
        assert overlay.running()
        assert (overlay.kind, overlay.animation.duration()) == (transition.SLIDE_LEFT, 1200)
        assert overlay.geometry() == window.image_view.rect()
        # The page gets its full time after the change has played.
        assert window.slideshow_timer.interval() == 5000 + 1200

        # Turning the page by hand in the middle of a change ends it at once.
        window.navigate(1)
        assert not overlay.running()

        window.transition_actions[transition.NONE].trigger()
        window.navigate(-1)
        window.slideshow_timer.timeout.emit()
        assert window.index == 2
        assert not overlay.running()
    finally:
        window.close()


def test_a_change_ends_by_itself(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        window.transition_speed_actions[300].trigger()
        window.slideshow_action.trigger()
        window.slideshow_timer.timeout.emit()
        overlay = window.transition_overlay
        assert overlay.running()
        app = QApplication.instance()
        deadline = monotonic() + 5
        while overlay.running():
            assert monotonic() < deadline, "the change never finished"
            app.processEvents()
        assert overlay.before.isNull() and overlay.after.isNull()
    finally:
        window.close()


def tick(window: app_module.MainWindow) -> int:
    window.slideshow_timer.timeout.emit()
    return window.index


def test_looping_goes_back_to_the_first_page(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    saved: list[ViewerSettings] = []
    window = make_window(monkeypatch, saved)
    try:
        window.open_path(tmp_path / "book" / "1.png")
        window.slideshow_loop_action.trigger()
        assert saved[-1].slideshow_loop is True
        window.slideshow_action.trigger()
        assert [tick(window) for _ in range(5)] == [2, 0, 1, 2, 0]
        assert window.slideshow_action.isChecked()
        assert window.current_folder == tmp_path / "book"
    finally:
        window.close()


def test_shuffle_shows_every_page_once_then_stops(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book", pages=8)
    saved: list[ViewerSettings] = []
    window = make_window(monkeypatch, saved)
    try:
        window.open_path(tmp_path / "book" / "3.png")
        window.slideshow_random_action.trigger()
        assert saved[-1].slideshow_random is True
        # Fixed, so "not simply in order" below cannot fail by an unlucky deal.
        app_module.random.seed(1)
        window.slideshow_action.trigger()
        seen = [tick(window) for _ in range(7)]
        # The other seven pages, each exactly once, and not simply in order.
        assert sorted(seen) == [0, 1, 2, 4, 5, 6, 7]
        assert seen != [4, 5, 6, 7, 0, 1, 2] and seen != sorted(seen)
        assert window.slideshow_action.isChecked()

        last = window.index
        assert tick(window) == last
        assert not window.slideshow_action.isChecked()
    finally:
        window.close()


def test_shuffle_with_looping_deals_again_without_repeating_a_page(
    tmp_path: Path, monkeypatch
) -> None:
    make_book(tmp_path / "book", pages=5)
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        window.slideshow_random_action.trigger()
        window.slideshow_loop_action.trigger()
        window.slideshow_action.trigger()
        seen = [0] + [tick(window) for _ in range(40)]
        assert window.slideshow_action.isChecked()
        # Never the same page twice running, and every page keeps coming up.
        assert all(first != second for first, second in zip(seen, seen[1:], strict=False))
        assert set(seen[-10:]) | set(seen[:10]) == {0, 1, 2, 3, 4}
        # Each full round holds every other page once.
        assert sorted(seen[1:5]) == [1, 2, 3, 4]
    finally:
        window.close()


def test_shuffle_deals_again_in_another_folder(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book", pages=4)
    for number in range(1, 4):
        Image.new("RGB", (20, 20)).save(tmp_path / "next" / f"{number}.png")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "book" / "0.png")
        window.slideshow_random_action.trigger()
        window.slideshow_action.trigger()
        tick(window)
        # Moving to another folder mid-show must not end it on the old deck.
        window.open_path(tmp_path / "next" / "0.png")
        seen = [tick(window) for _ in range(3)]
        assert sorted(seen) == [1, 2, 3]
        assert window.current_folder == tmp_path / "next"
    finally:
        window.close()


def test_the_toolbar_and_status_bar_show_a_running_slideshow(
    tmp_path: Path, monkeypatch
) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch)
    try:
        window.show()
        window.open_path(tmp_path / "book" / "0.png")
        button, label = window.slideshow_button_action, window.slideshow_label
        assert button.text() == "▶ スライドショー"
        assert not label.isVisible()

        button.trigger()
        assert window.slideshow_action.isChecked()
        assert button.text() == "■ スライドショーを停止"
        assert label.isVisible()
        assert label.text() == "▶ スライドショー中（5秒ごと）"
        window.slideshow_interval_actions[10].trigger()
        assert label.text() == "▶ スライドショー中（10秒ごと）"
        # A status message does not push the indicator off the bar.
        window.statusBar().showMessage("…")
        assert label.isVisible()

        # Clicking the indicator stops the show.
        QTest.mouseClick(label, Qt.MouseButton.LeftButton)
        assert not window.slideshow_action.isChecked()
        assert not window.slideshow_timer.isActive()
        assert button.text() == "▶ スライドショー"
        assert not label.isVisible()

        # Running into the last page clears both as well.
        window.go_to_index(2)
        button.trigger()
        tick(window)
        assert button.text() == "▶ スライドショー" and not label.isVisible()
    finally:
        window.close()
