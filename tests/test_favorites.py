from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QContextMenuEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox

import local_media_viewer.app as app_module
import local_media_viewer.favorites as favorites_module
from local_media_viewer.favorites import (
    center_square_crop,
    decode_square_thumbnail,
    decode_thumbnail,
    normalize_thumbnail,
)
from local_media_viewer.settings import Favorite, ViewerSettings


def wheel_event(widget) -> QWheelEvent:
    spot = QPoint(20, 20)
    return QWheelEvent(
        QPointF(spot),
        widget.mapToGlobal(spot),
        QPoint(0, -120),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def save_image(path: Path, color: str) -> None:
    Image.new("RGB", (12, 8), color).save(path)


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def test_favorite_shows_folder_name_and_registration_thumbnail(
    tmp_path: Path, monkeypatch
) -> None:
    folder = tmp_path / "作品集"
    folder.mkdir()
    save_image(folder / "1.png", "red")
    save_image(folder / "2.png", "blue")

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        window.add_favorite()

        assert len(window.favorites_menu.buttons) == 1
        button = window.favorites_menu.buttons[0]
        assert button.text() == "作品集"
        assert not button.icon().isNull()

        favorite = window.favorites[0]
        assert favorite.folder == str(folder)
        assert favorite.path == str(folder / "1.png")
        registered = decode_thumbnail(favorite.thumbnail)
        assert not registered.isNull()

        # Moving on to another image must not rewrite the stored thumbnail.
        window.navigate(1)
        assert window.files[window.index].name == "2.png"
        assert window.favorites[0].thumbnail == favorite.thumbnail
    finally:
        window.close()


def test_center_square_crop_takes_the_shorter_side_from_the_center() -> None:
    QApplication.instance() or QApplication([])
    pixmap = QPixmap(100, 40)
    pixmap.fill(QColor("#336699"))

    cropped = center_square_crop(pixmap)

    assert cropped.width() == 40
    assert cropped.height() == 40


def legacy_thumbnail_data() -> str:
    """A base64 PNG shaped like thumbnails stored before square cropping
    existed: letterboxed to a non-square, oddly sized rectangle."""
    QApplication.instance() or QApplication([])
    pixmap = QPixmap(12, 8)
    pixmap.fill(QColor("#336699"))
    letterboxed = pixmap.scaled(
        64,
        40,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    assert letterboxed.width() != letterboxed.height()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    letterboxed.save(buffer, "PNG")
    return bytes(buffer.data().toBase64()).decode("ascii")


def test_decode_square_thumbnail_squares_and_resizes_an_old_letterboxed_thumbnail() -> None:
    """Thumbnails stored before square cropping was added kept the original
    aspect ratio and whatever size the source image happened to produce
    (see encode_thumbnail's history); decoding one for display must still
    come out square and at the current thumbnail size, so rows of old and
    new entries line up instead of looking mismatched."""
    squared = decode_square_thumbnail(legacy_thumbnail_data())
    assert squared.width() == squared.height() == favorites_module.THUMBNAIL_SIZE.width()


def test_normalize_thumbnail_rescales_a_legacy_thumbnail(monkeypatch) -> None:
    normalized_data = normalize_thumbnail(legacy_thumbnail_data())
    normalized = decode_thumbnail(normalized_data)
    assert normalized.width() == normalized.height() == favorites_module.THUMBNAIL_SIZE.width()


def test_normalize_thumbnail_leaves_an_empty_thumbnail_alone() -> None:
    assert normalize_thumbnail("") == ""


def test_opening_the_app_normalizes_legacy_favorite_thumbnails(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    legacy = Favorite(id="a", folder="/legacy", name="legacy", thumbnail=legacy_thumbnail_data())
    monkeypatch.setattr(app_module, "load_settings", lambda: ViewerSettings(favorites=[legacy]))
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)

    window = app_module.MainWindow()
    try:
        migrated = decode_thumbnail(window.favorites[0].thumbnail)
        assert migrated.width() == migrated.height() == favorites_module.THUMBNAIL_SIZE.width()
    finally:
        window.close()


def test_favorite_thumbnail_and_menu_icon_are_square(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "作品集"
    folder.mkdir()
    save_image(folder / "1.png", "red")  # 12x8, not square

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        window.add_favorite()

        favorite = window.favorites[0]
        stored = decode_thumbnail(favorite.thumbnail)
        assert stored.width() == stored.height()

        button = window.favorites_menu.buttons[0]
        assert not button.icon().isNull()
    finally:
        window.close()


def test_clicking_the_remove_button_releases_that_entry(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "works"
    folder.mkdir()
    save_image(folder / "1.png", "red")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        window.add_favorite()
        assert len(window.favorites_menu.remove_buttons) == 1

        window.favorites_menu.remove_buttons[0].click()
        app.processEvents()  # the entry reports itself once the popup has closed

        assert window.favorites == []
        assert window.favorites_menu.buttons == []
    finally:
        window.close()


def test_removing_keeps_the_menu_open_and_renumbers_the_rest(
    tmp_path: Path, monkeypatch
) -> None:
    folders = []
    for name in ("a", "b", "c"):
        folder = tmp_path / name
        folder.mkdir()
        save_image(folder / "1.png", "red")
        folders.append(folder)

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.show()
        for folder in folders:
            window.open_path(folder / "1.png")
            window.add_favorite()
        menu = window.favorites_menu
        menu.popup(QPoint(0, 0))
        app.processEvents()

        menu.remove_buttons[0].click()
        app.processEvents()
        assert menu.isVisible()
        assert [f.name for f in window.favorites] == ["b", "c"]
        assert [b.text() for b in menu.buttons] == ["b", "c"]

        # The later entries were renumbered, so this removes "c", not a stale index.
        menu.remove_buttons[1].click()
        app.processEvents()
        assert menu.isVisible()
        assert [f.name for f in window.favorites] == ["b"]

        menu.buttons[0].click()
        app.processEvents()
        assert window.current_folder == folders[1]

        menu.close()
        app.processEvents()
        app.processEvents()
        assert [b.text() for b in menu.buttons] == ["b"]
        assert not window.favorites_stale
    finally:
        window.close()


def test_favorite_reopens_folder_and_can_be_removed(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "1"
    second = tmp_path / "2"
    for target in (first, second):
        target.mkdir()
    save_image(first / "first.png", "red")
    save_image(second / "second.png", "blue")

    window = make_window(monkeypatch)
    try:
        window.open_path(first / "first.png")
        window.add_favorite()
        window.open_path(second / "second.png")
        assert window.current_folder == second

        window.open_favorite(0)
        assert window.current_folder == first
        assert window.files[window.index].name == "first.png"

        window.remove_favorite(0)
        assert window.favorites == []
        assert window.favorites_menu.buttons == []
    finally:
        window.close()


def test_favorites_survive_a_settings_round_trip(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "保存"
    folder.mkdir()
    save_image(folder / "only.png", "green")
    stored: list[ViewerSettings] = []

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", stored.append)
    window = app_module.MainWindow()
    try:
        window.open_path(folder / "only.png")
        window.add_favorite()
    finally:
        window.close()

    assert stored[-1].favorites == window.favorites

    monkeypatch.setattr(app_module, "load_settings", lambda: stored[-1])
    restored = app_module.MainWindow()
    try:
        assert [item.folder for item in restored.favorites] == [str(folder)]
        assert restored.favorites_menu.buttons[0].text() == "保存"
        assert not restored.favorites_menu.buttons[0].icon().isNull()
    finally:
        restored.close()


def test_missing_neighbour_folder_keeps_the_current_image(tmp_path: Path, monkeypatch) -> None:
    only = tmp_path / "1"
    only.mkdir()
    save_image(only / "only.png", "red")

    def fail(*args, **kwargs):
        raise AssertionError("境界では通知を表示しない")

    window = make_window(monkeypatch)
    monkeypatch.setattr(QMessageBox, "information", fail)
    monkeypatch.setattr(QMessageBox, "question", fail)
    monkeypatch.setattr(QMessageBox, "warning", fail)
    try:
        window.open_path(only / "only.png")
        pixmap = window.image_view.item.pixmap()

        window.navigate(-1)
        window.navigate(1)

        assert window.current_folder == only
        assert window.files[window.index].name == "only.png"
        assert window.image_view.item.pixmap().cacheKey() == pixmap.cacheKey()
    finally:
        window.close()


class StubMenu:
    """Stands in for QMenu so the menu flows run without a modal popup."""

    pick: str | None = None

    def __init__(self, _parent=None) -> None:
        self.labels: list[str] = []
        self.by_label: dict[str, object] = {}
        self.submenus: list[tuple[str, StubMenu]] = []
        self.shared_actions: list = []

    def addAction(self, text: str) -> object:
        action = object()
        self.labels.append(text)
        self.by_label[text] = action
        return action

    def addMenu(self, text: str) -> "StubMenu":
        submenu = StubMenu()
        self.submenus.append((text, submenu))
        return submenu

    def addActions(self, actions) -> None:
        self.shared_actions = list(actions)

    def addSeparator(self) -> None:
        return None

    def exec(self, _position=None) -> object | None:
        if StubMenu.pick is None:
            return self.by_label[self.labels[0]] if self.labels else None
        for source in (self, *(menu for _text, menu in self.submenus)):
            if StubMenu.pick in source.by_label:
                return source.by_label[StubMenu.pick]
        return None

    def deleteLater(self) -> None:
        pass


def test_right_click_menu_registers_the_folder(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "右クリック"
    folder.mkdir()
    save_image(folder / "only.png", "red")

    menus: list[StubMenu] = []

    def make_menu(parent=None) -> StubMenu:
        menu = StubMenu(parent)
        menus.append(menu)
        return menu

    window = make_window(monkeypatch)
    monkeypatch.setattr(app_module, "QMenu", make_menu)
    try:
        window.open_path(folder / "only.png")
        viewport = window.image_view.viewport()
        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            QPoint(10, 10),
            viewport.mapToGlobal(QPoint(10, 10)),
        )

        QApplication.sendEvent(viewport, event)
        assert menus[-1].labels == ["お気に入りに登録"]
        assert [item.folder for item in window.favorites] == [str(folder)]
        assert window.favorites_menu.buttons[0].text() == "右クリック"
    finally:
        window.close()


def test_the_same_folder_can_be_registered_more_than_once(
    tmp_path: Path, monkeypatch
) -> None:
    folder = tmp_path / "重複"
    folder.mkdir()
    save_image(folder / "1.png", "red")
    save_image(folder / "2.png", "blue")

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        window.add_favorite()
        window.navigate(1)
        window.add_favorite()

        assert [item.folder for item in window.favorites] == [str(folder), str(folder)]
        assert [item.path for item in window.favorites] == [
            str(folder / "1.png"),
            str(folder / "2.png"),
        ]
        # Each registration keeps the frame it was made from.
        assert window.favorites[0].thumbnail != window.favorites[1].thumbnail
        assert [button.text() for button in window.favorites_menu.buttons] == ["重複", "重複"]

        # Releasing one entry leaves the other registration for the same folder.
        window.remove_favorite(0)
        assert [item.path for item in window.favorites] == [str(folder / "2.png")]
        assert len(window.favorites_menu.buttons) == 1
    finally:
        window.close()


def test_menu_entry_opens_its_registration(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "1"
    second = tmp_path / "2"
    for target in (first, second):
        target.mkdir()
    save_image(first / "first.png", "red")
    save_image(second / "second.png", "blue")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.open_path(first / "first.png")
        window.add_favorite()
        window.open_path(second / "second.png")
        window.add_favorite()
        assert [button.text() for button in window.favorites_menu.buttons] == ["1", "2"]

        window.favorites_menu.buttons[0].click()
        app.processEvents()  # the entry reports itself once the popup has closed
        assert window.current_folder == first
        assert window.files[window.index].name == "first.png"
    finally:
        window.close()


def test_right_clicking_a_menu_entry_releases_that_entry(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "重複"
    folder.mkdir()
    save_image(folder / "1.png", "red")
    save_image(folder / "2.png", "blue")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    monkeypatch.setattr(favorites_module, "QMenu", StubMenu)
    try:
        window.open_path(folder / "1.png")
        window.add_favorite()
        window.navigate(1)
        window.add_favorite()

        menu = window.favorites_menu
        menu.popup(QPoint(0, 0))
        app.processEvents()
        second = menu.buttons[1]
        position = second.mapTo(menu, QPoint(5, 5))
        menu.contextMenuEvent(
            QContextMenuEvent(
                QContextMenuEvent.Reason.Mouse, position, menu.mapToGlobal(position)
            )
        )
        app.processEvents()

        # Only the entry that was right-clicked goes away.
        assert [item.path for item in window.favorites] == [str(folder / "1.png")]
        assert len(window.favorites_menu.buttons) == 1
    finally:
        window.close()


def test_the_toolbar_cannot_be_hidden_from_a_right_click(tmp_path: Path, monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        # QMainWindow would otherwise offer a checkbox that hides the toolbar for good.
        assert window.createPopupMenu() is None
        assert window.toolbar.isVisible() or not window.isVisible()
    finally:
        window.close()


def open_favorites(window) -> QPoint:
    """Drop the お気に入り menu from the menu bar; returns where it should sit."""
    bar = window.menuBar()
    title = window.favorites_menu.menuAction()
    area = bar.actionGeometry(title)
    corner = bar.mapToGlobal(QPoint(area.left(), area.top() + area.height()))
    bar.setActiveAction(title)
    QApplication.processEvents()
    return corner


def test_the_favorites_menu_drops_below_its_title(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "メニュー"
    folder.mkdir()
    save_image(folder / "only.png", "red")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.show()
        app.processEvents()
        window.open_path(folder / "only.png")
        window.add_favorite()

        corner = open_favorites(window)
        menu = window.favorites_menu
        assert menu.isVisible()
        assert menu.pos() == corner
        # Registering sits above the list, and is offered once a folder is open.
        assert menu.actions()[0] is window.register_favorite_action
        assert window.register_favorite_action.isEnabled()
        menu.close()
    finally:
        window.close()


def test_a_long_list_scrolls_without_moving_the_popup(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "たくさん"
    folder.mkdir()
    for number in range(30):
        save_image(folder / f"{number}.png", "red")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.show()
        app.processEvents()
        window.open_path(folder / "0.png")
        for _ in range(30):
            window.add_favorite()
            window.navigate(1)
        assert len(window.favorites) == 30

        open_favorites(window)
        menu = window.favorites_menu
        entries = menu.entry_list

        # The popup shows a window onto the list, and the rest is reachable by
        # scrolling rather than clipped away.
        assert entries.height() < entries.row_height() * len(window.favorites)
        bar = entries.verticalScrollBar()
        assert bar.maximum() > 0

        anchored = menu.pos()
        for _ in range(4):
            menu.wheelEvent(wheel_event(menu))
            app.processEvents()
        assert bar.value() > 0
        # The reported bug: QMenu's own scrolling walks the popup up the screen.
        assert menu.pos() == anchored
        menu.close()
    finally:
        window.close()


def test_entries_can_be_moved_into_a_folder(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "整理"
    folder.mkdir()
    save_image(folder / "1.png", "red")
    save_image(folder / "2.png", "blue")

    window = make_window(monkeypatch)
    try:
        window.open_path(folder / "1.png")
        window.add_favorite()
        window.navigate(1)
        window.add_favorite()

        window.move_favorite(0, "風景")
        assert window.favorites[0].group == "風景"
        assert window.favorites[1].group == ""

        menu = window.favorites_menu
        # The group becomes a submenu, and the ungrouped entry stays at the top level.
        assert [submenu.title() for submenu in menu.group_menus] == ["風景 (1)"]
        assert len(menu.group_menus[0].buttons) == 1
        assert len(menu.buttons) == 1

        # Moving it back out empties the group again.
        window.move_favorite(0, "")
        assert window.favorites_menu.group_menus == []
        assert len(window.favorites_menu.buttons) == 2
    finally:
        window.close()


def test_right_clicking_an_entry_offers_the_existing_folders(
    tmp_path: Path, monkeypatch
) -> None:
    folder = tmp_path / "移動"
    folder.mkdir()
    save_image(folder / "1.png", "red")
    save_image(folder / "2.png", "blue")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    monkeypatch.setattr(favorites_module, "QMenu", StubMenu)
    try:
        window.open_path(folder / "1.png")
        window.add_favorite()
        window.navigate(1)
        window.add_favorite()
        window.move_favorite(0, "風景")

        menu = window.favorites_menu
        menu.popup(QPoint(0, 0))
        app.processEvents()
        target = menu.buttons[0]  # the ungrouped entry
        position = target.mapTo(menu, QPoint(5, 5))
        monkeypatch.setattr(StubMenu, "pick", "風景")
        menu.contextMenuEvent(
            QContextMenuEvent(
                QContextMenuEvent.Reason.Mouse, position, menu.mapToGlobal(position)
            )
        )
        app.processEvents()

        assert [item.group for item in window.favorites] == ["風景", "風景"]
        assert [submenu.title() for submenu in window.favorites_menu.group_menus] == ["風景 (2)"]
    finally:
        window.close()


def test_a_long_menu_still_opens_under_the_label(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "位置"
    folder.mkdir()
    for number in range(30):
        save_image(folder / f"{number}.png", "red")

    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.show()
        app.processEvents()
        window.open_path(folder / "0.png")
        for _ in range(30):
            window.add_favorite()
            window.navigate(1)

        available = window.screen().availableGeometry()
        # Park the window low enough that the full list cannot fit underneath.
        window.move(window.x(), available.bottom() - 460)
        app.processEvents()

        corner = open_favorites(window)

        menu = window.favorites_menu
        # Qt would lift the popup over the menu bar to fit; it must stay under the
        # title. Only the height is ours: on a narrow screen Qt may still slide it
        # sideways to keep its right edge on screen, which is fine.
        assert menu.pos().y() == corner.y()
        assert menu.pos().y() + menu.height() <= available.bottom() + 1
        assert menu.height() < menu.buttons[0].sizeHint().height() * len(window.favorites)
        menu.close()
    finally:
        window.close()
