from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.placement import LEFT, RIGHT, carried_over, centered, half
from local_media_viewer.settings import ViewerSettings


def make_window(monkeypatch, settings: ViewerSettings | None = None) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    saved: list[ViewerSettings] = []
    monkeypatch.setattr(app_module, "load_settings", lambda: settings or ViewerSettings())
    monkeypatch.setattr(app_module, "save_settings", saved.append)
    window = app_module.MainWindow()
    window.saved = saved
    return window


def test_halves_split_the_work_area_without_a_gap() -> None:
    area = QRect(0, 0, 2561, 1392)
    left, right = half(area, LEFT), half(area, RIGHT)
    assert left == QRect(0, 0, 1280, 1392)
    # The odd pixel goes to the right, so the halves meet and fill the area.
    assert right == QRect(1280, 0, 1281, 1392)
    # A second display to the left of the main one has negative coordinates.
    assert half(QRect(-1920, 0, 1920, 1040), RIGHT) == QRect(-960, 0, 960, 1040)


def test_centering_shrinks_a_frame_too_big_for_the_screen() -> None:
    area = QRect(0, 0, 1000, 800)
    assert centered(area, QSize(400, 200)) == QRect(300, 300, 400, 200)
    assert centered(area, QSize(1200, 900)) == area


def test_carrying_over_keeps_the_relative_place_and_size() -> None:
    main = QRect(0, 0, 2560, 1392)
    small = QRect(2560, 0, 1280, 696)
    # The left half of the big screen becomes the left half of the small one.
    assert carried_over(QRect(0, 0, 1280, 1392), main, small) == QRect(2560, 0, 640, 696)
    # Never left hanging off the far edge.
    moved = carried_over(QRect(2000, 1000, 560, 392), main, small)
    assert moved.right() <= small.right() and moved.bottom() <= small.bottom()


def test_the_window_menu_sits_right_of_favorites(monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        titles = [action.text() for action in window.menuBar().actions()]
        assert titles[-2:] == ["お気に入り(&A)", "ウィンドウ(&W)"]
        texts = [
            action.text() for action in window.window_menu.actions() if not action.isSeparator()
        ]
        assert texts == [
            "全画面表示\tEnter",
            "常に手前に表示",
            "最大化",
            "画面の左半分に配置",
            "画面の右半分に配置",
            "画面の中央に移動",
            "次のディスプレイへ移動",
        ]
        window.prepare_window_menu()
        # Only offered when there is another display to go to.
        assert window.next_screen_action.isEnabled() == (len(QApplication.screens()) > 1)
    finally:
        window.close()


def test_snapping_puts_the_whole_frame_on_half_the_screen(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.resize(700, 500)
        window.show()
        app.processEvents()
        area = window.screen().availableGeometry()

        window.snap_left_action.trigger()
        app.processEvents()
        # The frame, title bar included, not just the client area.
        assert window.frameGeometry() == half(area, LEFT)

        window.maximize_action.trigger()
        app.processEvents()
        assert window.isMaximized()

        # Snapping from maximized drops the maximized state first.
        window.snap_right_action.trigger()
        app.processEvents()
        assert not window.isMaximized()
        assert window.frameGeometry() == half(area, RIGHT)
    finally:
        window.close()


def test_always_on_top_is_remembered_and_keeps_the_window_shown(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.show()
        app.processEvents()
        window.always_on_top_action.setChecked(True)
        app.processEvents()
        # QWidget.setWindowFlag would have re-created the window hidden.
        assert window.isVisible()
        assert window.windowHandle().flags() & Qt.WindowType.WindowStaysOnTopHint
        assert window.saved[-1].always_on_top is True
    finally:
        window.close()

    restored = make_window(monkeypatch, ViewerSettings(always_on_top=True))
    try:
        assert restored.always_on_top_action.isChecked()
        assert restored.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    finally:
        restored.close()
