from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QContextMenuEvent, QShowEvent, QIcon, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from local_media_viewer.i18n import tr
from local_media_viewer.settings import Favorite

THUMBNAIL_SIZE = QSize(40, 40)
LABEL_LIMIT = 24
VISIBLE_ENTRIES = 10
MINIMUM_ENTRIES = 3

# Only reached with a pathological number of groups, and still better than the
# extra columns Qt would otherwise lay a too-tall menu out in.
MENU_STYLE = "QMenu { menu-scrollable: 1; }"

LIST_STYLE = (
    "QScrollArea { background: transparent; border: none; }"
    "QScrollArea > QWidget > QWidget { background: transparent; }"
)

ENTRY_STYLE = (
    "QToolButton { border: none; padding: 4px 14px 4px 8px; text-align: left; }"
    "QToolButton:hover { background: palette(highlight); color: palette(highlighted-text); }"
)

REMOVE_STYLE = (
    "QToolButton { border: none; padding: 4px 10px; color: palette(mid); font-weight: bold; }"
    "QToolButton:hover { background: #e04040; color: white; }"
)


def center_square_crop(pixmap: QPixmap) -> QPixmap:
    """Crop to a square around the center, keeping the shorter side in full.

    Applied both when a thumbnail is first stored and whenever an older,
    letterboxed one is displayed, so every entry ends up the same square
    shape regardless of when it was registered.
    """
    if pixmap.isNull():
        return pixmap
    size = pixmap.size()
    side = min(size.width(), size.height())
    if side <= 0:
        return pixmap
    x = (size.width() - side) // 2
    y = (size.height() - side) // 2
    return pixmap.copy(x, y, side, side)


def encode_thumbnail(pixmap: QPixmap) -> str:
    """Shrink the displayed frame and store it as base64 PNG inside the settings."""
    if pixmap.isNull():
        return ""
    scaled = center_square_crop(pixmap).scaled(
        THUMBNAIL_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not scaled.save(buffer, "PNG"):
        return ""
    return bytes(buffer.data().toBase64()).decode("ascii")


def decode_thumbnail(data: str) -> QPixmap:
    pixmap = QPixmap()
    if data:
        pixmap.loadFromData(QByteArray.fromBase64(data.encode("ascii")), "PNG")
    return pixmap


def decode_square_thumbnail(data: str) -> QPixmap:
    """decode_thumbnail(), cropped and rescaled to THUMBNAIL_SIZE for display.

    Thumbnails stored before square cropping was added are still
    letterboxed (aspect-ratio preserved) and sized to whatever their source
    image happened to produce; normalizing both here means every entry
    displays as the same uniform square without needing to re-register it.
    """
    cropped = center_square_crop(decode_thumbnail(data))
    if cropped.isNull():
        return cropped
    return cropped.scaled(
        THUMBNAIL_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def normalize_thumbnail(data: str) -> str:
    """Re-encode an already-stored thumbnail to the current square shape and size.

    Meant for a one-time migration of favorites registered before square
    cropping existed, so the normalized result is saved back into settings
    rather than recomputed from decode_square_thumbnail() on every display.
    """
    if not data:
        return data
    return encode_thumbnail(decode_thumbnail(data))


def favorite_label(favorite: Favorite) -> str:
    name = favorite.name or Path(favorite.folder).name or favorite.folder
    return name if len(name) <= LABEL_LIMIT else f"{name[: LABEL_LIMIT - 1]}…"


def group_names(favorites: list[Favorite]) -> list[str]:
    return sorted({favorite.group for favorite in favorites if favorite.group})


class FavoritesList(QScrollArea):
    """Carries the entry buttons of one menu.

    A menu capped with setMaximumHeight clips its overflow away unreachably,
    and QMenu's own scrolling drags the popup across the screen, so the entries
    scroll inside this widget instead and the popup itself never moves.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet(LIST_STYLE)
        self.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setAutoFillBackground(False)
        self.column = QVBoxLayout(content)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(0)
        self.setWidget(content)
        # `rows` sizes the list (each row also carries the remove button);
        # `buttons` keeps just the entry buttons, for row_height().
        self.rows: list[QWidget] = []
        self.buttons: list[QToolButton] = []

    def add(self, row: QWidget, button: QToolButton) -> None:
        self.column.addWidget(row)
        self.rows.append(row)
        self.buttons.append(button)

    def row_height(self) -> int:
        return self.buttons[0].sizeHint().height() if self.buttons else 0

    def fit(self, rows: int) -> None:
        if not self.rows:
            return
        rows = max(1, min(rows, len(self.rows)))
        self.setFixedHeight(rows * self.row_height())
        width = max(row.sizeHint().width() for row in self.rows)
        if rows < len(self.rows):
            width += self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        self.setFixedWidth(width)

    def fit_within(self, room: int) -> None:
        if not self.rows:
            return
        rows = room // self.row_height()
        self.fit(max(MINIMUM_ENTRIES, min(VISIBLE_ENTRIES, rows)))


class FavoritesMenu(QMenu):
    """The menu bar's favorites menu, also used for each group submenu."""

    activated = Signal(int)
    remove_requested = Signal(int)
    move_requested = Signal(int, str)
    new_group_requested = Signal(int)

    def __init__(self, title: str = "") -> None:
        super().__init__(title)
        self.setStyleSheet(MENU_STYLE)
        self.root: FavoritesMenu | None = None
        self.buttons: list[QToolButton] = []
        self.remove_buttons: list[QToolButton] = []
        self.entry_index: dict[QToolButton, int] = {}
        self.entry_list: FavoritesList | None = None
        self.group_menus: list[FavoritesMenu] = []
        self.groups: list[str] = []
        # Put back above the entries on every rebuild; owned by the window, so
        # clear() leaves them alive.
        self.leading: list[QAction] = []
        # Where the popup belongs (under its menu-bar title); None leaves the
        # placement to Qt, as for the group submenus.
        self.anchor: Callable[[], QPoint] | None = None
        self.entry_action: QWidgetAction | None = None

    def set_favorites(self, favorites: list[Favorite]) -> None:
        self.reset()
        if self.leading:
            self.addActions(self.leading)
            self.addSeparator()
        self.groups = group_names(favorites)
        if not favorites:
            empty = self.addAction(tr("お気に入りはありません"))
            empty.setEnabled(False)
        else:
            loose = [
                (index, item) for index, item in enumerate(favorites) if not item.group
            ]
            for name in self.groups:
                members = [
                    (index, item)
                    for index, item in enumerate(favorites)
                    if item.group == name
                ]
                self.add_group(name, members)
            if self.group_menus and loose:
                self.addSeparator()
            self.add_entries(loose)

    def add_group(self, name: str, members: list[tuple[int, Favorite]]) -> None:
        submenu = FavoritesMenu(f"{name} ({len(members)})")
        submenu.root = self
        submenu.groups = self.groups
        submenu.add_entries(members)
        submenu.activated.connect(self.activated)
        submenu.remove_requested.connect(self.remove_requested)
        submenu.move_requested.connect(self.move_requested)
        submenu.new_group_requested.connect(self.new_group_requested)
        if members:
            submenu.setIcon(QIcon(decode_square_thumbnail(members[0][1].thumbnail)))
        self.addMenu(submenu)
        self.group_menus.append(submenu)

    def add_entries(self, members: list[tuple[int, Favorite]]) -> None:
        if not members:
            return
        self.entry_list = FavoritesList()
        for index, favorite in members:
            button = self._make_button(favorite, index)
            row, remove_button = self._make_row(button, index)
            self.entry_list.add(row, button)
            self.buttons.append(button)
            self.remove_buttons.append(remove_button)
            self.entry_index[button] = index
        self.entry_list.fit(VISIBLE_ENTRIES)
        action = QWidgetAction(self)
        action.setDefaultWidget(self.entry_list)
        self.addAction(action)
        self.entry_action = action

    def reset(self) -> None:
        self.clear()  # also destroys the widgets held by the entry actions
        self.buttons.clear()
        self.remove_buttons.clear()
        self.entry_index.clear()
        self.entry_list = None
        self.entry_action = None
        for submenu in self.group_menus:
            submenu.reset()
            submenu.deleteLater()
        self.group_menus.clear()

    def limit_to(self, available: int) -> None:
        """Keep the popup short enough to open below its button, never over it."""
        if self.entry_list is None:
            return
        overhead = self.sizeHint().height() - self.entry_list.height()
        self.entry_list.fit_within(max(0, available - overhead))
        # QMenu measures its items once and re-measures only when an action
        # changes; a resized entry list does not count, so nudge the action.
        self.entry_action.setVisible(False)
        self.entry_action.setVisible(True)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self.anchor is None:
            return
        corner = self.anchor()
        if self.y() != corner.y():
            # QMenuBar decides between below and above its title from the size
            # the menu had before aboutToShow trimmed the list, so a long list
            # gets lifted over the bar; the trimmed menu does fit below.
            self.move(self.x(), corner.y())

    def _make_button(self, favorite: Favorite, index: int) -> QToolButton:
        button = QToolButton()
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(THUMBNAIL_SIZE)
        button.setIcon(QIcon(decode_square_thumbnail(favorite.thumbnail)))
        button.setText(favorite_label(favorite))
        button.setToolTip(f"{favorite.path or favorite.folder}\n{tr('右クリックで解除・フォルダ分け')}")
        button.setAutoRaise(True)
        button.setStyleSheet(ENTRY_STYLE)
        button.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False: self.choose(index))
        return button

    def _make_row(self, button: QToolButton, index: int) -> tuple[QWidget, QToolButton]:
        """Pair an entry button with a visible remove button, side by side."""
        remove = QToolButton()
        remove.setText("×")
        remove.setToolTip(tr("お気に入りから解除"))
        remove.setAutoRaise(True)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.setStyleSheet(REMOVE_STYLE)
        remove.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        remove.clicked.connect(lambda _checked=False: self.remove(index))

        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(button)
        layout.addWidget(remove)
        return row, remove

    def choose(self, index: int) -> None:
        self.close_chain()
        self.report(lambda: self.activated.emit(index))

    def remove(self, index: int) -> None:
        self.close_chain()
        self.report(lambda: self.remove_requested.emit(index))

    def close_chain(self) -> None:
        self.close()
        if self.root is not None:
            self.root.close()

    def report(self, emit) -> None:
        # Let the popup finish closing first: acting on an entry rebuilds the
        # menu, which destroys the very widgets it is still running on.
        QTimer.singleShot(0, emit)

    def wheelEvent(self, event: QWheelEvent) -> None:
        # Never fall through to QMenu's own scrolling: it drags the popup up
        # the screen instead of moving the entries. Scroll the list itself.
        if self.entry_list is not None:
            angles = event.angleDelta()
            bar = self.entry_list.verticalScrollBar()
            bar.setValue(bar.value() - (angles.y() or angles.x()))
        event.accept()

    def index_at(self, position: QPoint) -> int:
        widget = self.childAt(position)
        while widget is not None:
            index = self.entry_index.get(widget)
            if index is not None:
                return index
            widget = widget.parentWidget()
        return -1

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        # Entries are addressed by position, so the same folder can be
        # registered more than once and each copy managed on its own.
        index = self.index_at(event.pos())
        event.accept()
        if index < 0:
            return
        context = QMenu(self)
        remove = context.addAction(tr("お気に入りから解除"))
        move = context.addMenu(tr("フォルダへ移動"))
        targets = {move.addAction(tr("（フォルダなし）")): ""}
        for name in self.groups:
            targets[move.addAction(name)] = name
        move.addSeparator()
        create = move.addAction(tr("新しいフォルダ…"))
        chosen = context.exec(event.globalPos())
        context.deleteLater()
        if chosen is None:
            return
        self.close_chain()
        if chosen is remove:
            self.report(lambda: self.remove_requested.emit(index))
        elif chosen is create:
            self.report(lambda: self.new_group_requested.emit(index))
        elif chosen in targets:
            group = targets[chosen]
            self.report(lambda: self.move_requested.emit(index, group))
