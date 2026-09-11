from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QContextMenuEvent, QIcon, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from local_media_viewer.settings import Favorite

THUMBNAIL_SIZE = QSize(64, 40)
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

NO_GROUP_LABEL = "（フォルダなし）"
NEW_GROUP_LABEL = "新しいフォルダ…"


def encode_thumbnail(pixmap: QPixmap) -> str:
    """Shrink the displayed frame and store it as base64 PNG inside the settings."""
    if pixmap.isNull():
        return ""
    scaled = pixmap.scaled(
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
        self.buttons: list[QToolButton] = []

    def add(self, button: QToolButton) -> None:
        self.column.addWidget(button)
        self.buttons.append(button)

    def row_height(self) -> int:
        return self.buttons[0].sizeHint().height() if self.buttons else 0

    def fit(self, rows: int) -> None:
        if not self.buttons:
            return
        rows = max(1, min(rows, len(self.buttons)))
        self.setFixedHeight(rows * self.row_height())
        width = max(button.sizeHint().width() for button in self.buttons)
        if rows < len(self.buttons):
            width += self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        self.setFixedWidth(width)

    def fit_within(self, room: int) -> None:
        if not self.buttons:
            return
        rows = room // self.row_height()
        self.fit(max(MINIMUM_ENTRIES, min(VISIBLE_ENTRIES, rows)))


class FavoritesMenu(QMenu):
    """The toolbar's favorites drop-down, also used for each group submenu."""

    activated = Signal(int)
    remove_requested = Signal(int)
    move_requested = Signal(int, str)
    new_group_requested = Signal(int)

    def __init__(self, title: str = "お気に入り") -> None:
        super().__init__(title)
        self.setStyleSheet(MENU_STYLE)
        self.root: FavoritesMenu | None = None
        self.buttons: list[QToolButton] = []
        self.entry_index: dict[QToolButton, int] = {}
        self.entry_list: FavoritesList | None = None
        self.group_menus: list[FavoritesMenu] = []
        self.groups: list[str] = []

    def set_favorites(
        self,
        favorites: list[Favorite],
        options: list[QAction] | None = None,
    ) -> None:
        self.reset()
        self.groups = group_names(favorites)
        if not favorites:
            empty = self.addAction("お気に入りはありません")
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
        self.add_options(options or [])

    def add_options(self, options: list[QAction]) -> None:
        """Settings live under the favorites, separated by a rule.

        The actions belong to the window, so clear() only unlinks them here
        and the same objects stay shared with the right-click menu.
        """
        if not options:
            return
        self.addSeparator()
        self.addActions(options)

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
            submenu.setIcon(QIcon(decode_thumbnail(members[0][1].thumbnail)))
        self.addMenu(submenu)
        self.group_menus.append(submenu)

    def add_entries(self, members: list[tuple[int, Favorite]]) -> None:
        if not members:
            return
        self.entry_list = FavoritesList()
        for index, favorite in members:
            button = self._make_button(favorite, index)
            self.entry_list.add(button)
            self.buttons.append(button)
            self.entry_index[button] = index
        self.entry_list.fit(VISIBLE_ENTRIES)
        action = QWidgetAction(self)
        action.setDefaultWidget(self.entry_list)
        self.addAction(action)

    def reset(self) -> None:
        self.clear()  # also destroys the widgets held by the entry actions
        self.buttons.clear()
        self.entry_index.clear()
        self.entry_list = None
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

    def _make_button(self, favorite: Favorite, index: int) -> QToolButton:
        button = QToolButton()
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(THUMBNAIL_SIZE)
        button.setIcon(QIcon(decode_thumbnail(favorite.thumbnail)))
        button.setText(favorite_label(favorite))
        button.setToolTip(f"{favorite.path or favorite.folder}\n右クリックで解除・フォルダ分け")
        button.setAutoRaise(True)
        button.setStyleSheet(ENTRY_STYLE)
        button.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False: self.choose(index))
        return button

    def choose(self, index: int) -> None:
        self.close_chain()
        self.report(lambda: self.activated.emit(index))

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
        remove = context.addAction("お気に入りから解除")
        move = context.addMenu("フォルダへ移動")
        targets = {move.addAction(NO_GROUP_LABEL): ""}
        for name in self.groups:
            targets[move.addAction(name)] = name
        move.addSeparator()
        create = move.addAction(NEW_GROUP_LABEL)
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
