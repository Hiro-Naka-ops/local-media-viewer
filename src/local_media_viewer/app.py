from __future__ import annotations

import random
import sys
import uuid
from collections import OrderedDict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import perf_counter

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import (
    QByteArray,
    QCoreApplication,
    QEvent,
    QLibraryInfo,
    QLocale,
    QPoint,
    QRect,
    Qt,
    QTimer,
    QTranslator,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFileOpenEvent,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from local_media_viewer import i18n, ocr, transition
from local_media_viewer.appicon import app_icon, claim_taskbar_identity
from local_media_viewer.controls import ClickableLabel, SnappingSlider
from local_media_viewer.effects import EFFECT_LABELS, LINE_COLOR, NONE, apply_effect
from local_media_viewer.enhance import Enhancer
from local_media_viewer.favorites import FavoritesMenu, encode_thumbnail, normalize_thumbnail
from local_media_viewer.filmstrip import Filmstrip
from local_media_viewer.filters import FilterValues, apply_filters
from local_media_viewer.i18n import LANGUAGES, language_menu_title, tr
from local_media_viewer.mac_widget import (
    export_favorites_for_widget,
    parse_widget_favorite_id,
    resolve_favorite,
)
from local_media_viewer.media import (
    IMAGE_EXTENSIONS,
    SORT_LABELS,
    VIDEO_EXTENSIONS,
    SortOrder,
    file_times,
    listed_path,
    media_files,
    sibling_media_folder,
)
from local_media_viewer.placement import LEFT, RIGHT, carried_over, centered, half
from local_media_viewer.preloader import ImagePreloader, load_frame, load_image
from local_media_viewer.settings import (
    Favorite,
    ViewerSettings,
    load_settings,
    save_settings,
)
from local_media_viewer.sorticon import sort_icon
from local_media_viewer.spread import compose_spread, is_animated
from local_media_viewer.viewer import (
    FIT_HEIGHT,
    FIT_KINDS,
    FIT_WIDTH,
    FIT_WINDOW,
    NARROW_PERCENTS,
    PAN_TOP_CENTRE,
    ImageView,
    VideoView,
    narrow_kind,
)

STATUS_HINT_COLOR = "#98A2B3"
# The 表示サイズ entries: the three fits, then actual size. Labels are i18n keys.
ACTUAL_SIZE = "actual"
SIZE_LABELS = [
    (FIT_WINDOW, "ウィンドウに合わせる"),
    (FIT_WIDTH, "横幅に合わせる"),
    (FIT_HEIGHT, "縦幅に合わせる"),
    (ACTUAL_SIZE, "原寸で表示"),
]
# The 幅を固定 submenu: the picture's width pinned to a percentage of the
# view, centred, in 20% steps. Labels are i18n keys.
NARROW_WIDTH_LABELS = {
    100: "幅100%で固定",
    80: "幅80%で固定",
    60: "幅60%で固定",
    40: "幅40%で固定",
    20: "幅20%で固定",
}
NARROW_LABELS = [(narrow_kind(percent), NARROW_WIDTH_LABELS[percent]) for percent in NARROW_PERCENTS]
# The パン位置 modes: where a new page opens. Labels are i18n keys.
PAN_TOP = "top"
PAN_KEEP = "keep"
PAN_FIXED = "fixed"
PAN_LABELS = [
    (PAN_TOP, "毎回先頭に戻す"),
    (PAN_KEEP, "前のページの位置を引き継ぐ"),
    (PAN_FIXED, "固定した位置に合わせる"),
]
# Filter slider ranges; gamma is in hundredths (70 = 0.70).
BRIGHTNESS_RANGE = (-30, 30)
CONTRAST_RANGE = (-30, 30)
GAMMA_RANGE = (70, 130)
HUE_RANGE = (-30, 30)
# Seconds a page stays up in a slideshow: the choices in its menu, and how
# far "pick a number" may go.
SLIDESHOW_SECONDS = (1, 2, 3, 5, 10, 15, 30, 60)
SLIDESHOW_LIMIT = 3600
# Switched off for now: the user found the recognition too unreliable to offer
# (2026-10-01). The code and its tests stay; this hides the menu entries and
# the key. Set to True to bring it back.
OCR_ENABLED = False

# Qt's own strings (the Yes/No buttons, the colour dialog) come from these.
QT_TRANSLATIONS = {"ja": "qtbase_ja", "zh": "qtbase_zh_CN", "ko": "qtbase_ko"}
_qt_translator: QTranslator | None = None


def system_language() -> str:
    """The Windows display language, as a locale name such as ja_JP."""
    return QLocale.system().name()


def install_qt_translation(code: str) -> None:
    """Swap the translation Qt uses for the widgets it draws itself."""
    global _qt_translator
    if _qt_translator is not None:
        QCoreApplication.removeTranslator(_qt_translator)
        _qt_translator = None
    name = QT_TRANSLATIONS.get(code)
    if name is None:
        return
    translator = QTranslator()
    if translator.load(name, QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        QCoreApplication.installTranslator(translator)
        _qt_translator = translator


def format_file_time(value: float) -> str:
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")


class MainWindow(QMainWindow):
    def __init__(self, initial_path: Path | None = None) -> None:
        super().__init__()
        self.initializing = True
        self.settings = load_settings()
        self.current_folder: Path | None = None
        self.files: list[Path] = []
        self.index = -1
        self.image: Image.Image | None = None
        self.frame_index = 0
        self.animation_timer = QTimer(self)
        self.animation_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.animation_timer.timeout.connect(self.advance_animation)
        self.animation_cache: OrderedDict[int, tuple[QPixmap, int, int]] = OrderedDict()
        self.animation_cache_bytes = 0
        self.animation_cache_limit = 128 * 1024 * 1024
        self.preloader = ImagePreloader()
        # Writing settings serialises every favourite thumbnail, so paging does
        # not do it per page; the last turn within the window wins.
        self.settings_timer = QTimer(self)
        self.settings_timer.setSingleShot(True)
        self.settings_timer.setInterval(600)
        self.settings_timer.timeout.connect(self.persist_settings)
        self.spread_probe_cache: dict[Path, bool] = {}
        self.sort_order = SortOrder.parse(
            self.settings.sort_key, self.settings.sort_descending
        )
        self.folder_prompt_open = False
        self.favorites: list[Favorite] = list(self.settings.favorites)
        # Favorites registered before square thumbnails existed kept
        # whatever letterboxed, unevenly sized crop their source image
        # happened to produce, so their menu rows displayed at mismatched
        # sizes; normalize and save them once, now that ids etc. are settled.
        normalized = [
            replace(favorite, thumbnail=normalize_thumbnail(favorite.thumbnail))
            for favorite in self.favorites
        ]
        thumbnails_changed = [f.thumbnail for f in normalized] != [
            f.thumbnail for f in self.favorites
        ]
        self.favorites = normalized
        if thumbnails_changed:
            QTimer.singleShot(500, self.persist_settings)
        # Deferred: the widget only needs to catch up shortly after launch,
        # not before the window has had its first paint.
        QTimer.singleShot(500, lambda: export_favorites_for_widget(self.favorites))
        self.spread_second: Image.Image | None = None
        self.spread_anchor = max(0, self.settings.spread_anchor)
        self.displayed_pages: list[int] = []
        # Where the page being loaded should open, handed to set_pixmap.
        self.pending_pan: tuple[float, float] | None = None
        self.fixed_pan = (self.settings.pan_x, self.settings.pan_y)
        self.line_color = self.settings.line_color
        self.language_choice = self.settings.language
        self.apply_language(self.language_choice)

        self.setWindowTitle("Local Media Viewer")
        self.setWindowIcon(app_icon())
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self.image_view = ImageView()
        if self.settings.fit_kind in FIT_KINDS:
            self.image_view.fit_kind = self.settings.fit_kind
        self.video_view = VideoView()
        self.image_view.navigate.connect(self.navigate)
        self.video_view.navigate.connect(self.navigate)
        self.video_view.play_pause_requested.connect(self.toggle_video_playback)
        self.video_view.volume_change_requested.connect(self.change_volume)
        self.video_view.seek_requested.connect(self.seek_video)
        self.image_view.fullscreen_requested.connect(self.toggle_fullscreen)
        self.video_view.fullscreen_requested.connect(self.toggle_fullscreen)
        self.image_view.context_menu_requested.connect(self.show_media_menu)
        self.video_view.context_menu_requested.connect(self.show_media_menu)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.image_view)
        self.stack.addWidget(self.video_view)

        self.audio = QAudioOutput(self)
        self.audio.setVolume(self.settings.volume / 100)
        self.player = QMediaPlayer(self)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_view.surface)
        self.player.errorOccurred.connect(self.video_error)
        self.player.positionChanged.connect(self.video_view.update_position)
        self.player.durationChanged.connect(self.video_view.update_duration)
        self.player.playbackStateChanged.connect(self.show_playback_state)

        self.filter_panel = self.create_filter_panel()
        self.splitter = QSplitter()
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self.filter_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setSizes([980, 220])
        self.filmstrip = Filmstrip()
        self.filmstrip.selected.connect(self.select_filmstrip_item)
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.splitter, 1)
        central_layout.addWidget(self.filmstrip)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        # A permanent widget sits at the right-hand end of the status bar and is
        # left alone by showMessage, so the page count and the passing
        # notifications never overwrite the dates.
        # Added first, so it sits to the left of the dates it describes.
        # Leftmost of the permanent widgets, and shown only while a slideshow
        # runs: what says the pages are turning by themselves, and the place
        # to click to make them stop.
        self.slideshow_label = ClickableLabel()
        self.slideshow_label.setStyleSheet("font-weight: bold; padding-right: 12px;")
        self.slideshow_label.clicked.connect(lambda: self.slideshow_action.setChecked(False))
        self.slideshow_label.hide()
        self.statusBar().addPermanentWidget(self.slideshow_label)
        self.sort_icon_label = ClickableLabel()
        self.sort_icon_label.setStyleSheet("padding-right: 8px;")
        self.sort_icon_label.clicked.connect(self.show_sort_popup)
        self.statusBar().addPermanentWidget(self.sort_icon_label)
        self.file_times_label = QLabel()
        self.file_times_label.setStyleSheet(f"color: {STATUS_HINT_COLOR}; padding-right: 6px;")
        self.statusBar().addPermanentWidget(self.file_times_label)
        self.create_toolbar()
        self.retranslate_ui()
        self.restore_state(initial_path)
        self.initializing = False

    def create_toolbar(self) -> None:
        # Texts are filled in by retranslate_ui, so switching language can
        # relabel everything in place instead of rebuilding the window.
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        # The Windows 11 style fills a checked button with the accent colour,
        # which shouts over the picture; a quiet grey still reads as "on".
        self.toolbar.setStyleSheet(
            "QToolButton:checked { background: rgba(128, 128, 128, 0.35);"
            " border: none; border-radius: 4px; }"
        )
        self.addToolBar(self.toolbar)
        self.open_file_action = QAction(self)
        self.open_folder_action = QAction(self)
        self.previous_action = QAction(self)
        self.next_action = QAction(self)
        self.previous_action.setShortcuts(
            [
                QKeySequence(Qt.Key.Key_Left),
                QKeySequence(Qt.Key.Key_Up),
            ]
        )
        self.next_action.setShortcuts(
            [
                QKeySequence(Qt.Key.Key_Right),
                QKeySequence(Qt.Key.Key_Down),
            ]
        )
        self.previous_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.next_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.fit_action = QAction(self)
        self.fit_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        self.fit_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.open_file_action.triggered.connect(self.choose_file)
        self.open_folder_action.triggered.connect(self.choose_folder)
        self.previous_action.triggered.connect(lambda: self.navigate(-1))
        self.next_action.triggered.connect(lambda: self.navigate(1))
        self.fit_action.triggered.connect(self.image_view.toggle_fit)
        # Per page and never remembered: the clean-up takes a second or so, too
        # slow to run on every page turned, so it is asked for picture by picture.
        self.enhance_action = QAction(self)
        self.enhance_action.setCheckable(True)
        self.enhance_action.triggered.connect(self.toggle_enhance)
        self.enhancer = Enhancer()
        self.enhancer.ready.connect(self.show_enhanced)
        self.enhance_generation = 0
        # Display-only turns and flips, also per picture: they reset on the
        # next page (show_current), so a sideways photo never turns the rest
        # of the folder.
        self.rotation_path: Path | None = None
        self.orientation_menu = self.create_orientation_menu()
        # Reads the picture as it is on screen, on request only. Hidden where
        # the system has no OCR to offer (macOS, or no OCR language installed).
        self.ocr_action = QAction(self)
        self.ocr_action.setShortcut(QKeySequence("Ctrl+T"))
        self.ocr_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        # An invisible action's key does not fire either, so this hides Ctrl+T too.
        self.ocr_action.setVisible(self.ocr_offered())
        self.ocr_action.triggered.connect(self.read_text)
        self.ocr_reader = ocr.Reader()
        self.ocr_reader.ready.connect(self.show_read_text)
        self.ocr_dialog: ocr.TextDialog | None = None
        self.create_page_actions()
        self.size_menu = self.create_size_menu()
        # Only offered from the right-click menu, which is the one menu left
        # in full screen. Enter itself is handled by the shortcuts below: giving
        # this action the same keys would make them ambiguous and fire neither.
        self.fullscreen_action = QAction(self)
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.create_window_actions()
        self.filter_action = QAction(self)
        self.filter_action.setCheckable(True)
        self.filter_action.setChecked(self.settings.filter_panel_visible)
        self.filter_action.toggled.connect(self.toggle_filter_panel)
        self.filmstrip_action = QAction(self)
        self.filmstrip_action.setCheckable(True)
        self.filmstrip_action.setChecked(self.settings.filmstrip_visible)
        self.filmstrip_action.toggled.connect(self.toggle_filmstrip)
        self.toolbar_action = QAction(self)
        self.toolbar_action.setCheckable(True)
        self.toolbar_action.setChecked(self.settings.toolbar_visible)
        self.toolbar_action.toggled.connect(self.toggle_toolbar)
        self.status_bar_action = QAction(self)
        self.status_bar_action.setCheckable(True)
        self.status_bar_action.setChecked(self.settings.status_bar_visible)
        self.status_bar_action.toggled.connect(self.toggle_status_bar)
        self.option_groups = self.create_option_actions()
        self.option_actions = [
            action for group in self.option_groups for action in group
        ]
        self.language_menu = self.create_language_menu()
        self.play_action = QAction(self)
        self.play_action.triggered.connect(self.toggle_video_playback)
        self.stop_action = QAction(self)
        self.stop_action.triggered.connect(self.stop_video)
        self.mute_action = QAction(self)
        self.mute_action.setCheckable(True)
        self.mute_action.toggled.connect(self.audio.setMuted)
        self.volume_label = QLabel()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.settings.volume)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.open_file_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_folder_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.quit_action = QAction(self)
        self.quit_action.triggered.connect(self.close)
        self.create_menu_bar()
        # Full screen hides the menu bar and the toolbar, and an action's key
        # only fires while a widget holding it is visible, so the arrows and
        # Space did nothing in full screen. Held by the window as well, the
        # keys work whichever bars are showing.
        self.addActions(
            [
                self.previous_action,
                self.next_action,
                self.first_page_action,
                self.last_page_action,
                self.go_to_page_action,
                self.slideshow_action,
                self.fit_action,
                self.rotate_right_action,
                self.rotate_left_action,
                self.ocr_action,
                self.open_file_action,
                self.open_folder_action,
            ]
        )
        # Everything else lives in the menu bar; the toolbar keeps only what is
        # pressed over and over while reading. The video controls sit at the
        # far end, where appearing and vanishing shifts nothing else.
        self.toolbar.addActions([self.previous_action, self.next_action])
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.enhance_action)
        self.toolbar.addAction(self.slideshow_button_action)
        # Hidden through the QActions addWidget/addSeparator hand back: a
        # toolbar re-shows a widget it holds whenever it lays itself out, so
        # hiding the QSlider itself does not stick.
        self.video_toolbar_actions = [
            self.toolbar.addSeparator(),
            *self.add_toolbar_actions([self.play_action, self.stop_action, self.mute_action]),
            self.toolbar.addWidget(self.volume_label),
            self.toolbar.addWidget(self.volume_slider),
        ]
        self.show_video_controls(False)
        self.fullscreen_shortcuts = [
            QShortcut(QKeySequence(Qt.Key.Key_Return), self),
            QShortcut(QKeySequence(Qt.Key.Key_Enter), self),
        ]
        for shortcut in self.fullscreen_shortcuts:
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(self.toggle_fullscreen)
        self.toggle_filter_panel(self.settings.filter_panel_visible)
        self.toggle_filmstrip(self.settings.filmstrip_visible)
        self.toggle_toolbar(self.settings.toolbar_visible)
        self.toggle_status_bar(self.settings.status_bar_visible)

    def add_toolbar_actions(self, actions: list[QAction]) -> list[QAction]:
        self.toolbar.addActions(actions)
        return actions

    def show_video_controls(self, visible: bool) -> None:
        """Offer playback and sound only while a video is on screen.

        A still picture has nothing to play and no sound, so the controls would
        only take room on the toolbar and invite clicks that do nothing.
        """
        for action in self.video_toolbar_actions:
            action.setVisible(visible)

    def create_option_actions(self) -> list[list[QAction]]:
        """Settings shared by the 表示設定 menu and the right-click menu."""
        # "Pan" is the user-facing name for the drag position of a zoomed image.
        self.pan_menu = self.create_pan_menu()
        self.spread_action = QAction(self)
        self.spread_action.setCheckable(True)
        self.spread_action.setChecked(self.settings.spread_view)
        self.spread_action.toggled.connect(self.toggle_spread)
        self.spread_rtl_action = QAction(self)
        self.spread_rtl_action.setCheckable(True)
        self.spread_rtl_action.setChecked(self.settings.spread_rtl)
        self.spread_rtl_action.toggled.connect(self.change_spread_direction)
        self.spread_cover_action = QAction(self)
        self.spread_cover_action.setCheckable(True)
        self.spread_cover_action.setChecked(self.settings.spread_cover)
        self.spread_cover_action.toggled.connect(self.change_spread_cover)
        self.effect_menu = self.create_effect_menu()
        self.sort_menu = self.create_sort_menu()
        self.spread_shift_action = QAction(self)
        self.spread_shift_action.triggered.connect(self.shift_spread)
        # Ruled apart in the menus: the panels around the picture, how the
        # picture itself is drawn and ordered, then how pages are paired.
        return [
            [
                self.filmstrip_action,
                self.filter_action,
                self.toolbar_action,
                self.status_bar_action,
            ],
            [
                self.effect_menu.menuAction(),
                self.sort_menu.menuAction(),
                self.pan_menu.menuAction(),
            ],
            [
                self.spread_action,
                self.spread_rtl_action,
                self.spread_cover_action,
                self.spread_shift_action,
            ],
        ]

    def create_effect_menu(self) -> QMenu:
        """The エフェクト submenu: one choice at a time, plus its colour picker."""
        menu = QMenu(self)
        self.effect_actions: dict[str, QAction] = {}
        self.effect_choices = QActionGroup(self)
        self.effect_choices.setExclusive(True)
        for key, _label in EFFECT_LABELS:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(key == self.settings.effect)
            action.triggered.connect(lambda _checked=False, name=key: self.choose_effect(name))
            self.effect_choices.addAction(action)
            menu.addAction(action)
            self.effect_actions[key] = action
        if not any(action.isChecked() for action in self.effect_actions.values()):
            self.effect_actions[NONE].setChecked(True)
        menu.addSeparator()
        self.line_color_action = QAction(self)
        self.line_color_action.triggered.connect(self.choose_line_color)
        menu.addAction(self.line_color_action)
        return menu

    def create_sort_menu(self) -> QMenu:
        """The 並び順 submenu: one field at a time, plus the direction."""
        menu = QMenu(self)
        self.sort_actions: dict[str, QAction] = {}
        self.sort_choices = QActionGroup(self)
        self.sort_choices.setExclusive(True)
        for key, _label in SORT_LABELS:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(key == self.sort_order.key)
            action.triggered.connect(lambda _checked=False, name=key: self.choose_sort_key(name))
            self.sort_choices.addAction(action)
            menu.addAction(action)
            self.sort_actions[key] = action
        menu.addSeparator()
        self.sort_descending_action = QAction(self)
        self.sort_descending_action.setCheckable(True)
        self.sort_descending_action.setChecked(self.sort_order.descending)
        self.sort_descending_action.toggled.connect(self.change_sort_direction)
        menu.addAction(self.sort_descending_action)
        return menu

    def create_language_menu(self) -> QMenu:
        """The 言語 submenu: follow Windows, or one language picked outright."""
        menu = QMenu(self)
        self.language_actions: dict[str, QAction] = {}
        self.language_choices = QActionGroup(self)
        self.language_choices.setExclusive(True)
        for code, name in [(i18n.AUTO, ""), *LANGUAGES]:
            # A language's own name never changes with the UI language, so it is
            # set once here; only the "follow system" entry gets relabelled.
            action = QAction(name, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, value=code: self.choose_language(value)
            )
            self.language_choices.addAction(action)
            menu.addAction(action)
            self.language_actions[code] = action
            if code == i18n.AUTO:
                menu.addSeparator()
        chosen = self.language_actions.get(self.language_choice)
        (chosen or self.language_actions[i18n.AUTO]).setChecked(True)
        return menu

    def apply_language(self, choice: str) -> None:
        code = i18n.resolve(choice, system_language())
        i18n.set_language(code)
        install_qt_translation(code)

    def choose_language(self, choice: str) -> None:
        self.language_actions[choice].setChecked(True)
        if choice == self.language_choice:
            return
        self.language_choice = choice
        self.apply_language(choice)
        self.retranslate_ui()
        self.persist_settings()

    def retranslate_ui(self) -> None:
        """Put every label in the current language."""
        self.toolbar.setWindowTitle(tr("操作"))
        self.previous_action.setText(tr("前へ"))
        self.previous_action.setToolTip(f"{tr('前へ')} (← / ↑)")
        self.next_action.setText(tr("次へ"))
        self.next_action.setToolTip(f"{tr('次へ')} (→ / ↓)")
        self.fit_action.setText(tr("フィット／原寸"))
        self.fit_action.setToolTip(f"{tr('フィット／原寸')} (Space)")
        self.enhance_action.setText(tr("高画質化"))
        self.enhance_action.setToolTip(
            tr("この画像のブロックノイズを消して解像度を上げる（表示のみ・元ファイルは変更しない）")
        )
        self.ocr_action.setText(tr("文字を読み取る（OCR）"))
        if self.ocr_dialog is not None:
            self.ocr_dialog.retranslate()
        self.orientation_menu.setTitle(tr("回転・反転"))
        self.rotate_right_action.setText(tr("右に90°回転"))
        self.rotate_left_action.setText(tr("左に90°回転"))
        self.rotate_half_action.setText(tr("180°回転"))
        self.flip_horizontal_action.setText(tr("左右反転"))
        self.flip_vertical_action.setText(tr("上下反転"))
        self.size_menu.setTitle(tr("表示サイズ"))
        for key, label in SIZE_LABELS:
            self.size_actions[key].setText(tr(label))
        self.narrow_menu.setTitle(tr("幅を固定"))
        for key, label in NARROW_LABELS:
            self.size_actions[key].setText(tr(label))
        self.go_menu.setTitle(tr("移動(&G)"))
        self.first_page_action.setText(tr("最初のページ"))
        self.last_page_action.setText(tr("最後のページ"))
        self.go_to_page_action.setText(tr("ページを指定…"))
        self.slideshow_action.setText(tr("スライドショー"))
        self.show_slideshow_state()
        self.slideshow_settings_menu.setTitle(tr("スライドショーの設定"))
        self.slideshow_loop_action.setText(tr("最後まで行ったら最初に戻る"))
        self.slideshow_random_action.setText(tr("ランダム再生"))
        self.slideshow_menu.setTitle(tr("間隔"))
        for seconds, action in self.slideshow_interval_actions.items():
            action.setText(tr("{seconds}秒", seconds=seconds))
        self.show_slideshow_interval()
        self.transition_menu.setTitle(tr("切り替え効果"))
        for key, label in transition.TRANSITION_LABELS:
            self.transition_actions[key].setText(tr(label))
        for milliseconds, label in transition.SPEED_LABELS:
            self.transition_speed_actions[milliseconds].setText(tr(label))
        self.filter_action.setToolTip(f"{tr('フィルター')} (F)")
        self.filmstrip_action.setText(tr("フィルムストリップ"))
        self.toolbar_action.setText(tr("ツールバー"))
        self.status_bar_action.setText(tr("ステータスバー"))
        self.pan_menu.setTitle(tr("パン位置"))
        for key, label in PAN_LABELS:
            self.pan_actions[key].setText(tr(label))
        self.fix_pan_action.setText(tr("今の位置で固定する"))
        self.spread_action.setText(tr("見開き表示（2ページ）"))
        self.spread_rtl_action.setText(tr("見開きを右送りにする"))
        self.spread_cover_action.setText(tr("1ページ目を表紙として単独表示"))
        self.spread_shift_action.setText(tr("見開きページをずらす"))
        self.spread_shift_action.setToolTip(tr("組み合わせを1ページ分ずらす"))
        self.open_file_action.setText(tr("ファイルを開く…"))
        self.open_folder_action.setText(tr("フォルダを開く…"))
        self.quit_action.setText(tr("終了(&X)"))
        self.file_menu.setTitle(tr("ファイル(&F)"))
        self.view_menu.setTitle(tr("表示(&V)"))
        self.spread_menu.setTitle(tr("見開き(&S)"))
        self.favorites_menu.setTitle(tr("お気に入り(&A)"))
        self.window_menu.setTitle(tr("ウィンドウ(&W)"))
        self.always_on_top_action.setText(tr("常に手前に表示"))
        self.maximize_action.setText(tr("最大化"))
        self.snap_left_action.setText(tr("画面の左半分に配置"))
        self.snap_right_action.setText(tr("画面の右半分に配置"))
        self.center_action.setText(tr("画面の中央に移動"))
        self.next_screen_action.setText(tr("次のディスプレイへ移動"))
        self.register_favorite_action.setText(tr("お気に入りに登録"))
        # The keys are handled by shortcuts of their own (see create_toolbar);
        # the text after the tab only shows them in the menu's key column.
        self.fullscreen_action.setText(f"{tr('全画面表示')}\tEnter")
        self.filter_action.setText(f"{tr('フィルター')}\tF")
        self.effect_menu.setTitle(tr("エフェクト"))
        for key, label in EFFECT_LABELS:
            self.effect_actions[key].setText(tr(label))
        self.line_color_action.setText(tr("線の色を選ぶ…"))
        self.sort_menu.setTitle(tr("並び順"))
        for key, label in SORT_LABELS:
            self.sort_actions[key].setText(tr(label))
        self.sort_descending_action.setText(tr("降順"))
        self.language_menu.setTitle(language_menu_title())
        self.language_actions[i18n.AUTO].setText(tr("システムに合わせる"))
        self.show_playback_state()
        self.stop_action.setText(tr("■ 停止"))
        self.stop_action.setToolTip(tr("停止して先頭に戻す"))
        self.mute_action.setText(tr("ミュート"))
        self.volume_label.setText(tr("音量"))
        self.volume_slider.setToolTip(f"{tr('音量')}: {self.volume_slider.value()}")
        self.filter_title.setText(tr("表示フィルター"))
        self.filter_note.setText(tr("元ファイルは変更されません"))
        for label, text in self.filter_labels:
            label.setText(tr(text))
        for slider in (self.brightness, self.contrast, self.gamma, self.hue):
            slider.retranslate()
        self.reset_filters_button.setText(tr("フィルターをリセット"))
        self.video_filter_note.setText(tr("動画には初期版では適用されません"))
        self.show_sort_indicator()
        # The favorites menu writes its fixed texts as it fills itself.
        self.refresh_favorites()
        if 0 <= self.index < len(self.files):
            self.show_page_status()

    def choose_sort_key(self, name: str) -> None:
        self.sort_actions[name].setChecked(True)
        self.apply_sort_order(SortOrder(name, self.sort_descending_action.isChecked()))

    def change_sort_direction(self, descending: bool) -> None:
        self.apply_sort_order(SortOrder(self.sort_order.key, descending))

    def apply_sort_order(self, order: SortOrder) -> None:
        """Re-list the folder in a new order, staying on the same picture.

        The file being looked at is found again by path rather than by index,
        because reordering moves it; jumping to whatever landed on the old
        index would lose the reader's place.
        """
        if order == self.sort_order:
            return
        self.sort_order = order
        self.show_sort_indicator()
        self.persist_settings()
        if self.current_folder is None:
            return
        showing = self.files[self.index] if 0 <= self.index < len(self.files) else None
        files = media_files(self.current_folder, self.sort_order)
        if not files:
            return
        self.files = files
        self.index = files.index(showing) if showing in files else 0
        # The running order changed, so the pairing is counted afresh.
        self.spread_anchor = self.default_spread_anchor()
        self.show_current()

    def current_effect(self) -> str:
        for key, action in self.effect_actions.items():
            if action.isChecked():
                return key
        return NONE

    def choose_effect(self, name: str) -> None:
        self.effect_actions[name].setChecked(True)
        self.persist_settings()
        self.redraw_current_image()

    def choose_line_color(self) -> None:
        chosen = QColorDialog.getColor(
            QColor(self.line_color), self, tr("線の色"), QColorDialog.ColorDialogOption.DontUseNativeDialog
        )
        if not chosen.isValid():
            return
        self.line_color = chosen.name()
        # Picking a colour is also how this effect gets switched on.
        self.choose_effect(LINE_COLOR)

    def redraw_current_image(self) -> None:
        if self.stack.currentWidget() is not self.image_view:
            return
        if self.image is not None:
            self.clear_animation_cache()
            self.render_frame()
        elif not self.image_view.source_pixmap.isNull():
            # The page came in by the direct route, so there is no Pillow image
            # to re-render from: switching a filter or effect on reloads it.
            self.show_current()

    def create_pan_menu(self) -> QMenu:
        """パン位置: where each new page opens, and registering a fixed spot."""
        menu = QMenu(self)
        self.pan_actions: dict[str, QAction] = {}
        self.pan_choices = QActionGroup(self)
        self.pan_choices.setExclusive(True)
        saved = self.settings.pan_mode
        if saved not in (PAN_TOP, PAN_KEEP, PAN_FIXED):
            # Settings from before the modes: the old checkbox picked one of two.
            saved = PAN_TOP if self.settings.reset_pan_on_change else PAN_KEEP
        for key, _label in PAN_LABELS:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(key == saved)
            action.triggered.connect(lambda _checked=False, name=key: self.choose_pan_mode(name))
            self.pan_choices.addAction(action)
            menu.addAction(action)
            self.pan_actions[key] = action
        menu.addSeparator()
        self.fix_pan_action = QAction(self)
        self.fix_pan_action.triggered.connect(self.fix_pan_here)
        menu.addAction(self.fix_pan_action)
        return menu

    def pan_mode(self) -> str:
        for key, action in self.pan_actions.items():
            if action.isChecked():
                return key
        return PAN_TOP

    def choose_pan_mode(self, name: str) -> None:
        self.pan_actions[name].setChecked(True)
        self.persist_settings()

    def fix_pan_here(self) -> None:
        """Remember where the view is now as the spot every page opens at.

        A side that cannot scroll at the moment - the width, when fitted to
        it - keeps the proportion it had, so fixing the height of a page
        fitted to width does not quietly reset the other side.
        """
        horizontal, vertical = self.image_view.pan_fraction()
        old_x, old_y = self.fixed_pan
        self.fixed_pan = (
            old_x if horizontal is None else horizontal,
            old_y if vertical is None else vertical,
        )
        self.choose_pan_mode(PAN_FIXED)
        self.statusBar().showMessage(tr("この位置でパン位置を固定しました"), 3000)

    def pan_for_new_page(self) -> tuple[float, float] | None:
        mode = self.pan_mode()
        if mode == PAN_FIXED:
            return self.fixed_pan
        if mode == PAN_TOP:
            return PAN_TOP_CENTRE
        return None

    def default_spread_anchor(self) -> int:
        """Where pairing starts in a folder that was just opened.

        With the cover option on the anchor sits on the second page, which
        leaves page 1 on its own and runs the pairs 2-3, 4-5 from there.
        """
        return 1 if self.spread_cover_action.isChecked() else 0

    def toggle_spread(self, enabled: bool) -> None:
        if enabled:
            # The page it was switched on at becomes the first half of the
            # spread, except that a cover is left standing on its own.
            self.spread_anchor = (
                self.default_spread_anchor() if self.index <= 0 else self.index
            )
        self.persist_settings()
        self.show_current()

    def change_spread_direction(self, _right_to_left: bool) -> None:
        self.persist_settings()
        self.show_current()

    def change_spread_cover(self, _enabled: bool) -> None:
        self.spread_anchor = self.default_spread_anchor()
        self.persist_settings()
        self.show_current()

    def shift_spread(self) -> None:
        """Move the split one page along, swapping one half of the pair out.

        The page on the far side of the split stays on screen and becomes the
        first half of the new pair, so 2-3 becomes 3-4: one page is exchanged
        rather than the whole spread jumping. Anchoring on the current page
        instead would do nothing at all, because show_current leaves the index
        sitting on the first half of the pair already on screen.
        """
        if not self.spread_action.isChecked():
            self.spread_action.setChecked(True)  # toggle_spread anchors and redraws
            return
        target = min(self.index + 1, len(self.files) - 1)
        if target == self.index:
            return
        self.spread_anchor = target
        self.index = target
        self.persist_settings()
        self.show_current()

    def create_filter_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.filter_title = QLabel()
        self.filter_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.filter_note = QLabel()
        self.filter_note.setWordWrap(True)
        self.filter_note.setStyleSheet("color: #667085;")
        layout.addWidget(self.filter_title)
        layout.addWidget(self.filter_note)
        form = QFormLayout()
        # Narrow ranges on purpose: across the old ±100 (±180 for hue) one scale
        # mark moved a picture further than anyone wanted to adjust by, and the
        # far ends were never useful for reading. Each mark is now 3 (0.03 gamma).
        self.brightness = self.make_slider(*BRIGHTNESS_RANGE, self.settings.brightness, 0)
        self.contrast = self.make_slider(*CONTRAST_RANGE, self.settings.contrast, 0)
        self.gamma = self.make_slider(*GAMMA_RANGE, round(self.settings.gamma * 100), 100)
        self.hue = self.make_slider(*HUE_RANGE, self.settings.hue, 0)
        # Kept with their i18n keys so retranslate_ui can relabel the rows.
        self.filter_labels: list[tuple[QLabel, str]] = []
        for text, slider in [
            ("明るさ", self.brightness),
            ("コントラスト", self.contrast),
            ("ガンマ", self.gamma),
            ("色相", self.hue),
        ]:
            label = QLabel()
            form.addRow(label, slider)
            self.filter_labels.append((label, text))
        layout.addLayout(form)
        self.reset_filters_button = QPushButton()
        self.reset_filters_button.clicked.connect(self.reset_filters)
        layout.addWidget(self.reset_filters_button)
        self.video_filter_note = QLabel()
        self.video_filter_note.setWordWrap(True)
        self.video_filter_note.setStyleSheet("color: #98A2B3;")
        layout.addWidget(self.video_filter_note)
        layout.addStretch()
        return panel

    def make_slider(
        self,
        minimum: int,
        maximum: int,
        value: int,
        default: int,
        divisions: int = 20,
    ) -> SnappingSlider:
        slider = SnappingSlider(minimum, maximum, value, default, divisions)
        slider.valueChanged.connect(self.filters_changed)
        return slider

    def filter_values(self) -> FilterValues:
        return FilterValues(
            brightness=self.brightness.value(),
            contrast=self.contrast.value(),
            gamma=self.gamma.value() / 100,
            hue=self.hue.value(),
        )

    def reset_filters(self) -> None:
        for slider, value in [
            (self.brightness, 0),
            (self.contrast, 0),
            (self.gamma, 100),
            (self.hue, 0),
        ]:
            slider.setValue(value)

    def restore_state(self, initial_path: Path | None = None) -> None:
        if self.settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.settings.window_geometry.encode("ascii")))
        if initial_path is not None and initial_path.exists():
            self.open_path(initial_path)
            return
        last = Path(self.settings.last_path) if self.settings.last_path else None
        if last and last.is_file():
            self.open_path(last)

    def choose_file(self) -> None:
        start = str(self.current_folder or Path.home())
        selected, _ = QFileDialog.getOpenFileName(
            self, tr("画像・動画を開く"), start, f"{tr('メディアファイル')} (*)"
        )
        if selected:
            self.open_path(Path(selected))

    def choose_folder(self) -> None:
        start = str(self.current_folder or Path.home())
        selected = QFileDialog.getExistingDirectory(self, tr("フォルダを開く"), start)
        if selected:
            self.open_folder(Path(selected), 0)

    def resumed_folder(self) -> Path | None:
        """The folder the last session was left in, if there was one."""
        return Path(self.settings.last_path).parent if self.settings.last_path else None

    def enter_folder(self, folder: Path) -> None:
        """Move into a folder, starting its page pairing over.

        Each folder is its own book, so the spread is re-anchored rather than
        carrying another folder's offset across and pulling the new cover into
        a pair with the first inside page. The one exception is reopening the
        very folder the last session was left in, which resumes on the offset
        it was left on; a file handed in on the command line is a different
        book even at startup, so it does not inherit that offset.
        """
        if folder == self.current_folder:
            return
        resuming = self.initializing and folder == self.resumed_folder()
        self.current_folder = folder
        self.spread_probe_cache.clear()
        # The deck is of the folder left behind.
        self.slideshow_deck = None
        if not resuming:
            self.spread_anchor = self.default_spread_anchor()

    def open_path(self, path: Path) -> None:
        if path.is_dir():
            self.open_folder(path, 0)
            return
        files = media_files(path.parent, self.sort_order)
        listed = listed_path(files, path)
        if listed is None:
            QMessageBox.warning(
                self, tr("非対応形式"), tr("対応していないファイルです。\n{name}", name=path.name)
            )
            return
        path = listed
        self.enter_folder(path.parent)
        self.files = files
        self.index = files.index(path)
        self.show_current()

    def open_folder(self, folder: Path, index: int) -> None:
        files = media_files(folder, self.sort_order)
        if not files:
            QMessageBox.information(
                self, tr("メディアなし"), tr("対応ファイルがありません。\n{folder}", folder=folder)
            )
            return
        self.enter_folder(folder)
        self.files = files
        self.index = index if index >= 0 else len(files) - 1
        self.show_current()

    def spreadable(self, index: int) -> bool:
        """Whether a page can be half of a spread.

        Checked before pairing rather than after loading: a pair that silently
        collapsed to one page would renumber the halves and strand the partner.
        """
        path = self.files[index]
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            return False
        cached = self.spread_probe_cache.get(path)
        if cached is not None:
            return cached
        try:
            with Image.open(path) as probe:
                result = not is_animated(probe)
        except (OSError, ValueError):
            result = False
        # Opening both halves on every page turn re-read the headers each time;
        # the answer only depends on the file, so it is kept for the folder.
        self.spread_probe_cache[path] = result
        return result

    def spread_pages(self) -> list[int]:
        """The one or two file indices that make up the current view.

        Pairs are counted from the page the spread was switched on at, so that
        page stays the first half and the split never shifts by itself.
        """
        if not self.spread_action.isChecked():
            return [self.index]
        start = self.index - ((self.index - self.spread_anchor) % 2)
        pages = [page for page in (start, start + 1) if 0 <= page < len(self.files)]
        if len(pages) < 2 or not all(self.spreadable(page) for page in pages):
            return [self.index]
        return pages

    def load_second_page(self, index: int) -> None:
        path = self.files[index]
        try:
            # A spread is composed by Pillow, so the partner is always wanted as
            # a Pillow image even if the preloader happens to hold a QImage.
            frame = self.preloader.take(path, plain=False)
            self.spread_second = (
                frame.image if frame is not None and frame.image is not None else load_image(path)
            )
        except (OSError, ValueError):
            self.spread_second = None

    def show_current(self) -> None:
        if not (0 <= self.index < len(self.files)):
            return
        pages = self.spread_pages()
        self.index = pages[0]
        path = self.files[self.index]
        # A reading still under way is of the page being left.
        self.ocr_reader.cancel()
        # Whatever shows this page, a change still playing over the view is of
        # an older one. The slideshow starts its own after the page is up.
        self.transition_overlay.cancel()
        # A new page starts from the file as it is; the clean-up is per picture.
        self.enhancer.cancel()
        self.enhance_action.setChecked(False)
        self.enhance_generation = 0
        # Kept while the same page is only redrawn (a filter switched on, the
        # enhancement switched off), dropped as soon as another page shows.
        if path != self.rotation_path:
            self.rotation_path = None
            self.image_view.reset_orientation()
        self.filmstrip.set_files(self.files)
        self.filmstrip.set_current(self.index)
        self.stop_current()
        self.setWindowTitle(f"{path.name} — Local Media Viewer")
        self.settings.last_path = str(path)
        self.persist_settings_soon()
        self.displayed_pages = [self.index]
        is_video = path.suffix.lower() in VIDEO_EXTENSIONS
        self.show_video_controls(is_video)
        if is_video:
            self.stack.setCurrentWidget(self.video_view)
            self.video_view.prepare_media()
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.play()
            self.video_view.activate_controls()
        else:
            self.stack.setCurrentWidget(self.image_view)
            self.video_view.update_duration(0)
            try:
                plain = self.plain_view()
                frame = self.preloader.take(path, plain) or load_frame(path, plain)
                self.frame_index = 0
                self.pending_pan = self.pan_for_new_page()
                if frame.qimage is not None:
                    # Nothing for Pillow to do, so the decoded bitmap goes
                    # straight to the view.
                    self.image = None
                    self.image_view.set_pixmap(QPixmap.fromImage(frame.qimage), self.pending_pan)
                    self.pending_pan = None
                else:
                    self.image = frame.image
                    if len(pages) > 1:
                        self.load_second_page(pages[1])
                        # Keep the pair as the step unit even if the partner
                        # failed to load, so paging cannot stall on it.
                        self.displayed_pages = pages
                    self.render_frame()
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, tr("画像を開けません"), f"{path.name}\n{error}")
        self.enhance_action.setEnabled(self.can_enhance())
        self.orientation_menu.setEnabled(self.can_rotate())
        self.ocr_action.setEnabled(self.can_rotate())
        self.show_page_status()
        self.preload_nearby_images()
        self.restart_slideshow_timer()

    def can_rotate(self) -> bool:
        """A picture is on screen: a still, an animation or a spread, not a video."""
        return (
            self.stack.currentWidget() is self.image_view
            and not self.image_view.source_pixmap.isNull()
        )

    def ocr_offered(self) -> bool:
        return OCR_ENABLED and ocr.available()

    def read_text(self) -> None:
        """OCR the picture exactly as shown: turned, enhanced, a spread and all."""
        if not self.ocr_offered() or not self.can_rotate():
            return
        # What is on screen rather than the file: a sideways scan turned
        # upright reads, and a spread reads as its two pages.
        image = self.image_view.source_pixmap.toImage()
        self.ocr_reader.request(image)
        self.statusBar().showMessage(tr("文字を読み取っています…"))

    def show_read_text(self, generation: int, text: str | None) -> None:
        # Against the reader's own count, which show_current's cancel() bumps:
        # a result already queued when the page was turned belongs to the old page.
        if generation != self.ocr_reader.generation:
            return
        if text is None:
            self.statusBar().showMessage(tr("文字を読み取れませんでした"), 5000)
            return
        if not text.strip():
            self.statusBar().showMessage(tr("文字が見つかりませんでした"), 5000)
            return
        if self.ocr_dialog is None:
            self.ocr_dialog = ocr.TextDialog(self)
        names = " / ".join(self.files[page].name for page in self.displayed_pages or [self.index])
        self.ocr_dialog.show_text(names, text)
        self.statusBar().showMessage(
            tr("{count}行を読み取りました", count=text.count("\n") + 1), 4000
        )

    def create_orientation_menu(self) -> QMenu:
        """回転・反転: turns and flips of the picture on screen."""
        menu = QMenu(self)
        view = self.image_view
        self.rotate_right_action = QAction(self)
        self.rotate_right_action.setShortcut(QKeySequence("Ctrl+R"))
        self.rotate_right_action.triggered.connect(lambda: self.turn_view(view.rotate, 90))
        self.rotate_left_action = QAction(self)
        self.rotate_left_action.setShortcut(QKeySequence("Ctrl+L"))
        self.rotate_left_action.triggered.connect(lambda: self.turn_view(view.rotate, -90))
        self.rotate_half_action = QAction(self)
        self.rotate_half_action.triggered.connect(lambda: self.turn_view(view.rotate, 180))
        self.flip_horizontal_action = QAction(self)
        self.flip_horizontal_action.triggered.connect(
            lambda: self.turn_view(view.flip_horizontal)
        )
        self.flip_vertical_action = QAction(self)
        self.flip_vertical_action.triggered.connect(lambda: self.turn_view(view.flip_vertical))
        menu.addActions(
            [self.rotate_right_action, self.rotate_left_action, self.rotate_half_action]
        )
        menu.addSeparator()
        menu.addActions([self.flip_horizontal_action, self.flip_vertical_action])
        return menu

    def turn_view(self, change, *args: int) -> None:
        if not self.can_rotate():
            return
        self.rotation_path = self.files[self.index]
        change(*args)

    def can_enhance(self) -> bool:
        """A single still picture: not a video, an animation or a spread.

        An animation would come back as one frame, and a spread is two files.
        """
        if self.stack.currentWidget() is not self.image_view or len(self.displayed_pages) != 1:
            return False
        if self.image_view.source_pixmap.isNull():
            return False
        return self.image is None or int(getattr(self.image, "n_frames", 1)) == 1

    def current_pan(self) -> tuple[float, float]:
        horizontal, vertical = self.image_view.pan_fraction()
        return (
            0.5 if horizontal is None else horizontal,
            0.5 if vertical is None else vertical,
        )

    def toggle_enhance(self, checked: bool) -> None:
        if not checked:
            self.enhancer.cancel()
            if self.enhance_generation < 0:
                # Showing the cleaned copy: reload the file, staying where we were.
                pan = self.current_pan()
                self.show_current()
                self.image_view.set_pan_fraction(*pan)
            self.enhance_generation = 0
            return
        if not self.can_enhance():
            self.enhance_action.setChecked(False)
            return
        self.enhance_generation = self.enhancer.request(self.files[self.index])
        self.statusBar().showMessage(tr("高画質化しています…"))

    def show_enhanced(self, generation: int, image: Image.Image | None) -> None:
        if generation != self.enhance_generation or not self.enhance_action.isChecked():
            if image is not None:
                image.close()
            return
        if image is None:
            self.enhance_generation = 0
            self.enhance_action.setChecked(False)
            self.statusBar().showMessage(tr("高画質化できませんでした"), 5000)
            return
        pan = self.current_pan()
        self.animation_timer.stop()
        self.clear_animation_cache()
        if self.image is not None:
            self.image.close()
        # From here the page is drawn from the cleaned copy, so filters and
        # effects still apply on top of it (render_frame).
        self.image = image
        self.frame_index = 0
        self.pending_pan = pan
        self.render_frame()
        # Negative marks "the cleaned copy is on screen" for toggle_enhance().
        self.enhance_generation = -1
        self.show_page_status()
        self.statusBar().showMessage(
            tr("高画質化しました（{width}×{height}）", width=image.width, height=image.height),
            4000,
        )

    def plain_view(self) -> bool:
        """Whether the page can go from the decoder straight to the screen.

        With no filter, no effect and no spread there is nothing for Pillow to
        do, and routing the bitmap through it only to hand it back to Qt costs
        more than the decode itself.
        """
        return (
            self.filter_values() == FilterValues()
            and self.current_effect() == NONE
            and not self.spread_action.isChecked()
        )

    def show_page_status(self) -> None:
        pages = self.displayed_pages or [self.index]
        numbers = "-".join(str(page + 1) for page in pages)
        self.statusBar().showMessage(
            f"{numbers} / {len(self.files)}　{self.files[pages[0]]}"
        )
        self.show_file_times(self.files[pages[0]])

    def show_sort_indicator(self) -> None:
        """Mark the current order beside the dates it applies to.

        A picture rather than words: the status bar already carries a page
        count, a path and two timestamps, and another phrase among them reads
        as clutter.
        """
        pixmap = sort_icon(
            self.sort_order.key,
            self.sort_order.descending,
            self.sort_icon_label.fontMetrics().height(),
            STATUS_HINT_COLOR,
            self.devicePixelRatioF(),
        )
        self.sort_icon_label.setPixmap(pixmap)
        field = tr(dict(SORT_LABELS).get(self.sort_order.key, ""))
        way = tr("降順" if self.sort_order.descending else "昇順")
        self.sort_icon_label.setToolTip(
            f"{tr('並び順: {field}（{way}）', field=field, way=way)}\n{tr('クリックで並び順を変更')}"
        )

    def show_sort_popup(self) -> None:
        """Drop the 並び順 menu from the status-bar icon, opening upwards.

        The very menu the 表示 menu holds, so a choice made here is ticked
        there too. The icon sits on the window's bottom edge, so the menu is
        lifted to end at the icon's top and right-aligned to it, rather than
        left for Qt to flip after finding no room below.
        """
        label = self.sort_icon_label
        size = self.sort_menu.sizeHint()
        corner = label.mapToGlobal(QPoint(label.width(), 0))
        self.sort_menu.popup(QPoint(corner.x() - size.width(), corner.y() - size.height()))

    def show_file_times(self, path: Path) -> None:
        """Put the file's dates at the right-hand end of the status bar.

        The status bar is hidden along with the toolbar in full screen, so this
        follows it out of the way without needing to be handled separately.
        """
        times = file_times(path)
        if times is None:
            self.file_times_label.clear()
            return
        created, modified = times
        self.file_times_label.setText(
            tr(
                "作成 {created}　更新 {modified}",
                created=format_file_time(created),
                modified=format_file_time(modified),
            )
        )

    def preload_nearby_images(self) -> None:
        nearby: list[Path] = []
        for distance in range(1, 4):
            for target in (self.index + distance, self.index - distance):
                if 0 <= target < len(self.files):
                    path = self.files[target]
                    if path.suffix.lower() in IMAGE_EXTENSIONS:
                        nearby.append(path)
        self.preloader.preload(nearby, self.plain_view())

    def create_page_actions(self) -> None:
        """Home / End and the page-number jump, beside the arrow-key paging."""
        self.first_page_action = QAction(self)
        self.first_page_action.setShortcut(QKeySequence(Qt.Key.Key_Home))
        self.first_page_action.triggered.connect(lambda: self.go_to_index(0))
        self.last_page_action = QAction(self)
        self.last_page_action.setShortcut(QKeySequence(Qt.Key.Key_End))
        self.last_page_action.triggered.connect(lambda: self.go_to_index(len(self.files) - 1))
        self.go_to_page_action = QAction(self)
        self.go_to_page_action.setShortcut(QKeySequence("Ctrl+G"))
        self.go_to_page_action.triggered.connect(self.ask_page_number)
        for action in (self.first_page_action, self.last_page_action, self.go_to_page_action):
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.create_slideshow_actions()

    def create_slideshow_actions(self) -> None:
        """スライドショー: turn the page by itself every few seconds."""
        # Never remembered between runs: a viewer that starts turning pages by
        # itself on launch would be a surprise. Only the interval is saved.
        self.slideshow_action = QAction(self)
        self.slideshow_action.setCheckable(True)
        self.slideshow_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        self.slideshow_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.slideshow_action.toggled.connect(self.toggle_slideshow)
        # Single shot, restarted by show_current: a page turned by hand gets
        # its full time too, instead of whatever was left of the last one.
        self.slideshow_timer = QTimer(self)
        self.slideshow_timer.setSingleShot(True)
        self.slideshow_timer.timeout.connect(self.advance_slideshow)
        self.slideshow_video_waited = False
        # The toolbar's own button rather than slideshow_action again: a
        # button can say what pressing it does now ("stop"), which a ticked
        # menu entry sharing its words could not.
        self.slideshow_button_action = QAction(self)
        self.slideshow_button_action.triggered.connect(self.slideshow_action.toggle)
        self.slideshow_loop_action = QAction(self)
        self.slideshow_loop_action.setCheckable(True)
        self.slideshow_loop_action.setChecked(self.settings.slideshow_loop is True)
        self.slideshow_loop_action.toggled.connect(lambda _checked: self.persist_settings())
        self.slideshow_random_action = QAction(self)
        self.slideshow_random_action.setCheckable(True)
        self.slideshow_random_action.setChecked(self.settings.slideshow_random is True)
        self.slideshow_random_action.toggled.connect(self.change_slideshow_random)
        # Pages still to come in a shuffled slideshow; None until first needed.
        self.slideshow_deck: list[Path] | None = None
        saved = self.settings.slideshow_seconds
        # A hand-edited or damaged settings file must not make a zero-second loop.
        valid = type(saved) is int and 1 <= saved <= SLIDESHOW_LIMIT
        self.slideshow_seconds = saved if valid else 5
        self.slideshow_menu = QMenu(self)
        self.slideshow_interval_actions: dict[int, QAction] = {}
        self.slideshow_choices = QActionGroup(self)
        self.slideshow_choices.setExclusive(True)
        for seconds in SLIDESHOW_SECONDS:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(seconds == self.slideshow_seconds)
            action.triggered.connect(
                lambda _checked=False, value=seconds: self.choose_slideshow_seconds(value)
            )
            self.slideshow_choices.addAction(action)
            self.slideshow_menu.addAction(action)
            self.slideshow_interval_actions[seconds] = action
        self.slideshow_menu.addSeparator()
        self.slideshow_custom_action = QAction(self)
        self.slideshow_custom_action.setCheckable(True)
        self.slideshow_custom_action.triggered.connect(self.ask_slideshow_seconds)
        self.slideshow_choices.addAction(self.slideshow_custom_action)
        self.slideshow_menu.addAction(self.slideshow_custom_action)
        self.create_transition_menu()
        # One entry in the menus for everything that is set once and left.
        self.slideshow_settings_menu = QMenu(self)
        self.slideshow_settings_menu.addActions(
            [self.slideshow_loop_action, self.slideshow_random_action]
        )
        self.slideshow_settings_menu.addSeparator()
        self.slideshow_settings_menu.addMenu(self.slideshow_menu)
        self.slideshow_settings_menu.addMenu(self.transition_menu)

    def change_slideshow_random(self, _enabled: bool) -> None:
        self.slideshow_deck = None
        self.persist_settings()

    def show_slideshow_state(self) -> None:
        """Say on the toolbar and the status bar whether a slideshow is running."""
        running = self.slideshow_action.isChecked()
        self.slideshow_button_action.setText(
            tr("■ スライドショーを停止") if running else tr("▶ スライドショー")
        )
        self.slideshow_button_action.setToolTip(f"{tr('スライドショー')} (F5)")
        self.slideshow_label.setText(
            tr("▶ スライドショー中（{seconds}秒ごと）", seconds=self.slideshow_seconds)
        )
        self.slideshow_label.setToolTip(tr("クリックでスライドショーを停止"))
        self.slideshow_label.setVisible(running)

    def create_transition_menu(self) -> None:
        """スライドショーの切り替え効果: how a page gives way, and how fast."""
        effect = self.settings.slideshow_effect
        self.slideshow_effect = effect if effect in transition.TRANSITIONS else transition.FADE
        duration = self.settings.slideshow_effect_ms
        self.slideshow_effect_ms = duration if duration in transition.SPEEDS else 600
        self.transition_overlay = transition.TransitionOverlay(self.image_view)
        self.transition_menu = QMenu(self)
        self.transition_actions: dict[str, QAction] = {}
        self.transition_speed_actions: dict[int, QAction] = {}
        self.transition_choices = QActionGroup(self)
        self.transition_choices.setExclusive(True)
        for key, _label in transition.TRANSITION_LABELS:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(key == self.slideshow_effect)
            action.triggered.connect(
                lambda _checked=False, name=key: self.choose_transition(name)
            )
            self.transition_choices.addAction(action)
            self.transition_menu.addAction(action)
            self.transition_actions[key] = action
        self.transition_menu.addSeparator()
        self.transition_speed_choices = QActionGroup(self)
        self.transition_speed_choices.setExclusive(True)
        for milliseconds, _label in transition.SPEED_LABELS:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(milliseconds == self.slideshow_effect_ms)
            action.triggered.connect(
                lambda _checked=False, value=milliseconds: self.choose_transition_speed(value)
            )
            self.transition_speed_choices.addAction(action)
            self.transition_menu.addAction(action)
            self.transition_speed_actions[milliseconds] = action

    def choose_transition(self, name: str) -> None:
        self.slideshow_effect = name
        self.persist_settings()

    def choose_transition_speed(self, milliseconds: int) -> None:
        self.slideshow_effect_ms = milliseconds
        self.persist_settings()

    def show_slideshow_interval(self) -> None:
        """Tick the interval in use; a hand-picked one shows its number."""
        custom = self.slideshow_seconds not in SLIDESHOW_SECONDS
        for seconds, action in self.slideshow_interval_actions.items():
            action.setChecked(seconds == self.slideshow_seconds)
        self.slideshow_custom_action.setChecked(custom)
        self.slideshow_custom_action.setText(
            tr("秒数を指定…（{seconds}秒）", seconds=self.slideshow_seconds)
            if custom
            else tr("秒数を指定…")
        )

    def ask_slideshow_seconds(self) -> None:
        seconds, accepted = QInputDialog.getInt(
            self,
            tr("スライドショーの間隔"),
            tr("1ページを表示する秒数（1〜{limit}）:", limit=SLIDESHOW_LIMIT),
            self.slideshow_seconds,
            1,
            SLIDESHOW_LIMIT,
        )
        if accepted:
            self.choose_slideshow_seconds(seconds)
        else:
            # Clicking the entry ticked it; put the tick back where it belongs.
            self.show_slideshow_interval()

    def toggle_slideshow(self, enabled: bool) -> None:
        self.show_slideshow_state()
        if not enabled:
            self.slideshow_timer.stop()
            self.statusBar().showMessage(tr("スライドショーを停止しました"), 3000)
            return
        if not self.files:
            self.slideshow_action.setChecked(False)
            return
        # Each run deals afresh, so starting again never resumes a stale order.
        self.slideshow_deck = None
        self.restart_slideshow_timer()
        self.statusBar().showMessage(
            tr("スライドショーを開始しました（{seconds}秒ごと）", seconds=self.slideshow_seconds),
            3000,
        )

    def choose_slideshow_seconds(self, seconds: int) -> None:
        self.slideshow_seconds = seconds
        self.show_slideshow_interval()
        self.show_slideshow_state()
        self.persist_settings()
        self.restart_slideshow_timer()

    def restart_slideshow_timer(self) -> None:
        """Give the page on screen its full time, if a slideshow is running."""
        self.slideshow_video_waited = False
        if self.slideshow_action.isChecked():
            self.slideshow_timer.start(self.slideshow_seconds * 1000)

    def slideshow_blocked(self) -> bool:
        """A dialog or a menu is open: turning the page under it would pull the
        picture away from what the user is in the middle of choosing for it."""
        return (
            QApplication.activeModalWidget() is not None
            or QApplication.activePopupWidget() is not None
        )

    def next_slideshow_index(self) -> int | None:
        """The page a running slideshow shows next, or None when it is over."""
        shown = self.displayed_pages or [self.index]
        loop = self.slideshow_loop_action.isChecked()
        if not self.slideshow_random_action.isChecked():
            target = shown[-1] + 1
            if target < len(self.files):
                return target
            return 0 if loop else None
        # A shuffled deck, not a fresh roll of the dice each time: every page
        # comes up once before any comes up twice, and "all shown" has a meaning.
        # Paths rather than indexes, which a change of sort order would shift.
        current = {self.files[page] for page in shown}
        positions = {path: index for index, path in enumerate(self.files)}
        if self.slideshow_deck is None:
            self.slideshow_deck = self.dealt_deck(current)
        for _deal in range(2):
            while self.slideshow_deck:
                path = self.slideshow_deck.pop()
                if path in positions and path not in current:
                    return positions[path]
            if not loop:
                return None
            self.slideshow_deck = self.dealt_deck(current)
        # Looping with nothing else in the folder: stay on the page.
        return shown[0]

    def dealt_deck(self, current: set[Path]) -> list[Path]:
        deck = [path for path in self.files if path not in current]
        random.shuffle(deck)
        return deck

    def advance_slideshow(self) -> None:
        if not self.slideshow_action.isChecked():
            return
        if self.slideshow_blocked():
            self.slideshow_timer.start(self.slideshow_seconds * 1000)
            return
        if self.stack.currentWidget() is self.video_view and not self.slideshow_video_waited:
            # A video plays through once before moving on, however short the
            # interval. Only once: it loops, so "until it ends" has no end.
            remaining = self.player.duration() - self.player.position()
            if remaining > 0:
                self.slideshow_video_waited = True
                self.slideshow_timer.start(remaining)
                return
        # Not navigate(): past the last page that asks about the next folder,
        # and a question popping up unattended is not a way to end a slideshow.
        target = self.next_slideshow_index()
        if target is None:
            self.slideshow_action.setChecked(False)
            self.statusBar().showMessage(
                tr("すべてのページを表示したので、スライドショーを終了しました")
                if self.slideshow_random_action.isChecked()
                else tr("最後のページまで表示したので、スライドショーを終了しました"),
                5000,
            )
            return
        # Only between two pictures: a video is drawn by the player, which a
        # photograph of the view does not capture.
        animated = (
            self.slideshow_effect != transition.NONE
            and self.stack.currentWidget() is self.image_view
        )
        before = self.image_view.grab() if animated else None
        self.index = target
        self.show_current()
        if self.slideshow_deck:
            # A spread shows the drawn page's partner too; it has had its turn.
            together = {self.files[page] for page in self.displayed_pages}
            self.slideshow_deck = [path for path in self.slideshow_deck if path not in together]
        if before is not None and self.stack.currentWidget() is self.image_view:
            self.transition_overlay.play(
                self.slideshow_effect, self.slideshow_effect_ms, before, self.image_view.grab()
            )
            # The change is not part of the page's own time on screen.
            self.slideshow_timer.start(self.slideshow_seconds * 1000 + self.slideshow_effect_ms)

    def go_to_index(self, index: int) -> None:
        # show_current settles a spread onto the pair holding this page.
        if 0 <= index < len(self.files) and index != self.index:
            self.index = index
            self.show_current()

    def ask_page_number(self) -> None:
        if not self.files:
            return
        number, accepted = QInputDialog.getInt(
            self,
            tr("ページを指定"),
            tr("ページ番号（1〜{count}）:", count=len(self.files)),
            self.index + 1,
            1,
            len(self.files),
        )
        if accepted:
            self.go_to_index(number - 1)

    def create_size_menu(self) -> QMenu:
        """表示サイズ: which fit Space returns to, or actual size."""
        menu = QMenu(self)
        self.size_actions: dict[str, QAction] = {}
        self.size_choices = QActionGroup(self)
        # Optional: after a Ctrl+wheel zoom none of the four describes the view.
        self.size_choices.setExclusionPolicy(
            QActionGroup.ExclusionPolicy.ExclusiveOptional
        )
        for key in (FIT_WINDOW, FIT_WIDTH, FIT_HEIGHT, ACTUAL_SIZE):
            action = QAction(self)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, name=key: self.choose_size(name))
            self.size_choices.addAction(action)
            menu.addAction(action)
            self.size_actions[key] = action
        self.narrow_menu = QMenu(self)
        for key, _label in NARROW_LABELS:
            action = QAction(self)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, name=key: self.choose_size(name))
            self.size_choices.addAction(action)
            self.narrow_menu.addAction(action)
            self.size_actions[key] = action
        menu.addMenu(self.narrow_menu)
        menu.addSeparator()
        menu.addAction(self.fit_action)
        menu.aboutToShow.connect(self.show_size_state)
        return menu

    def choose_size(self, name: str) -> None:
        if name == ACTUAL_SIZE:
            self.image_view.original_size()
        else:
            self.image_view.set_fit_kind(name)
            self.persist_settings()
        self.show_size_state()

    def show_size_state(self) -> None:
        """Tick the entry describing the view as it is, which Space may have changed."""
        view = self.image_view
        if view.fit_mode:
            current = view.fit_kind
        elif view.display_scale == 1.0:
            current = ACTUAL_SIZE
        else:
            current = None
        for key, action in self.size_actions.items():
            action.setChecked(key == current)

    def create_menu_bar(self) -> None:
        """ファイル / 表示 / 移動 / 見開き / お気に入り / ウィンドウ, as Windows apps order them.

        The actions belong to the window, so the right-click menu shows the
        very same ones and their ticks stay in step without any syncing.
        """
        bar = self.menuBar()
        self.file_menu = bar.addMenu("")
        self.file_menu.addActions([self.open_file_action, self.open_folder_action])
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.quit_action)

        panels, drawing, spread = self.option_groups
        self.view_menu = bar.addMenu("")
        self.view_menu.addMenu(self.size_menu)
        self.view_menu.addMenu(self.orientation_menu)
        self.view_menu.addAction(self.ocr_action)
        for group in (panels, drawing):
            self.view_menu.addSeparator()
            self.view_menu.addActions(group)
        # Language lives here only: it is set once, not while reading, so it
        # has no place in the right-click menu.
        self.view_menu.addSeparator()
        self.view_menu.addMenu(self.language_menu)

        self.go_menu = bar.addMenu("")
        self.go_menu.addActions([self.previous_action, self.next_action])
        self.go_menu.addSeparator()
        self.go_menu.addActions([self.first_page_action, self.last_page_action])
        self.go_menu.addSeparator()
        self.go_menu.addAction(self.go_to_page_action)
        self.go_menu.addSeparator()
        self.go_menu.addAction(self.slideshow_action)
        self.go_menu.addMenu(self.slideshow_settings_menu)

        self.spread_menu = bar.addMenu("")
        self.spread_menu.addActions(spread)

        self.register_favorite_action = QAction(self)
        self.register_favorite_action.triggered.connect(self.add_favorite)
        self.favorites_stale = False
        self.favorites_menu = FavoritesMenu()
        self.favorites_menu.leading = [self.register_favorite_action]
        self.favorites_menu.anchor = self.favorites_anchor
        self.favorites_menu.activated.connect(self.open_favorite)
        self.favorites_menu.remove_requested.connect(self.remove_favorite)
        self.favorites_menu.move_requested.connect(self.move_favorite)
        self.favorites_menu.new_group_requested.connect(self.name_new_group)
        self.favorites_menu.aboutToShow.connect(self.prepare_favorites_menu)
        self.favorites_menu.aboutToHide.connect(self.rebuild_stale_favorites)
        bar.addMenu(self.favorites_menu)

        self.window_menu = bar.addMenu("")
        self.window_menu.addActions([self.fullscreen_action, self.always_on_top_action])
        self.window_menu.addSeparator()
        self.window_menu.addActions(
            [
                self.maximize_action,
                self.snap_left_action,
                self.snap_right_action,
                self.center_action,
            ]
        )
        self.window_menu.addSeparator()
        self.window_menu.addAction(self.next_screen_action)
        self.window_menu.aboutToShow.connect(self.prepare_window_menu)

    def create_window_actions(self) -> None:
        self.always_on_top_action = QAction(self)
        self.always_on_top_action.setCheckable(True)
        self.always_on_top_action.setChecked(self.settings.always_on_top)
        self.always_on_top_action.toggled.connect(self.set_always_on_top)
        # Set on the widget while it is still hidden; once shown, see
        # set_always_on_top for why the flag goes through the native window.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.settings.always_on_top)
        self.maximize_action = QAction(self)
        self.maximize_action.setCheckable(True)
        self.maximize_action.triggered.connect(self.toggle_maximized)
        self.snap_left_action = QAction(self)
        self.snap_left_action.triggered.connect(lambda: self.snap_to_half(LEFT))
        self.snap_right_action = QAction(self)
        self.snap_right_action.triggered.connect(lambda: self.snap_to_half(RIGHT))
        self.center_action = QAction(self)
        self.center_action.triggered.connect(self.center_on_screen)
        self.next_screen_action = QAction(self)
        self.next_screen_action.triggered.connect(self.move_to_next_screen)

    def prepare_window_menu(self) -> None:
        self.maximize_action.setChecked(self.isMaximized())
        self.fullscreen_action.setChecked(self.isFullScreen())
        # Displays come and go while the app runs, so this is asked each time.
        self.next_screen_action.setEnabled(len(QGuiApplication.screens()) > 1)

    def set_always_on_top(self, enabled: bool) -> None:
        handle = self.windowHandle()
        if handle is None:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        else:
            # QWidget.setWindowFlag on a shown window re-creates it hidden, so
            # the window would vanish until show(); the native window changes
            # its topmost state in place.
            handle.setFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.persist_settings()

    def leave_full_screen_or_maximized(self) -> None:
        if self.isFullScreen():
            self.toggle_fullscreen()  # also brings the bars and panels back
        if self.isMaximized():
            self.showNormal()

    def place_frame(self, frame: QRect) -> None:
        """Put the window's outer frame, title bar included, on the given rectangle.

        setGeometry places the client area, so the frame's own margins are
        taken off first; otherwise the title bar would hang over the top edge.
        """
        self.leave_full_screen_or_maximized()
        outer = self.frameGeometry()
        inner = self.geometry()
        self.setGeometry(
            frame.adjusted(
                inner.left() - outer.left(),
                inner.top() - outer.top(),
                inner.right() - outer.right(),
                inner.bottom() - outer.bottom(),
            )
        )

    def work_area(self) -> QRect:
        return self.screen().availableGeometry()

    def toggle_maximized(self) -> None:
        if self.isFullScreen():
            self.toggle_fullscreen()
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.maximize_action.setChecked(self.isMaximized())

    def snap_to_half(self, side: str) -> None:
        self.place_frame(half(self.work_area(), side))

    def center_on_screen(self) -> None:
        self.leave_full_screen_or_maximized()
        self.place_frame(centered(self.work_area(), self.frameGeometry().size()))

    def move_to_next_screen(self) -> None:
        screens = QGuiApplication.screens()
        if len(screens) < 2:
            return
        current = self.screen()
        target = screens[(screens.index(current) + 1) % len(screens)]
        full_screen = self.isFullScreen()
        maximized = self.isMaximized()
        self.leave_full_screen_or_maximized()
        self.place_frame(
            carried_over(
                self.frameGeometry(), current.availableGeometry(), target.availableGeometry()
            )
        )
        # A maximized or full-screen window is put back that way on the new
        # display, which is what dragging it across would have done.
        if maximized:
            self.showMaximized()
        if full_screen:
            self.toggle_fullscreen()

    def prepare_favorites_menu(self) -> None:
        self.register_favorite_action.setEnabled(self.current_folder is not None)
        # Trim the list to the room under the menu bar, so the popup can open
        # below its title rather than over the picture's top edge.
        top = self.favorites_anchor().y()
        self.favorites_menu.limit_to(self.menuBar().screen().availableGeometry().bottom() - top)

    def favorites_anchor(self) -> QPoint:
        bar = self.menuBar()
        title = bar.actionGeometry(self.favorites_menu.menuAction())
        return bar.mapToGlobal(QPoint(title.left(), title.top() + title.height()))

    def refresh_favorites(self) -> None:
        self.favorites_stale = False
        self.favorites_menu.set_favorites(self.favorites)

    def rebuild_stale_favorites(self) -> None:
        if self.favorites_stale:
            # After the popup has finished hiding: the rebuild destroys its widgets.
            QTimer.singleShot(0, self.refresh_favorites)

    def current_thumbnail(self) -> QPixmap:
        if self.stack.currentWidget() is self.video_view:
            return self.video_view.frame_pixmap()
        return self.image_view.source_pixmap

    def show_media_menu(self, position: QPoint) -> None:
        if self.current_folder is None:
            return
        menu = QMenu(self)
        register = menu.addAction(tr("お気に入りに登録"))
        menu.addSeparator()
        # The toolbar is gone in full screen, so this menu has to carry the way
        # back out as well as fitting, which is otherwise only on the toolbar.
        self.fullscreen_action.setChecked(self.isFullScreen())
        self.show_size_state()
        # The slideshow's settings come along: in full screen, where a
        # slideshow is mostly watched, this is the only menu there is.
        viewing = [
            self.size_menu.menuAction(),
            self.fullscreen_action,
            self.slideshow_action,
            self.slideshow_settings_menu.menuAction(),
        ]
        if self.stack.currentWidget() is self.image_view:
            viewing.extend(
                [self.orientation_menu.menuAction(), self.enhance_action, self.ocr_action]
            )
        menu.addActions(viewing)
        if self.stack.currentWidget() is self.video_view:
            # The toolbar is hidden in full screen, so playback is offered here too.
            menu.addSeparator()
            menu.addActions([self.play_action, self.stop_action, self.mute_action])
        for group in self.option_groups:
            menu.addSeparator()
            menu.addActions(group)
        chosen = menu.exec(position)
        menu.deleteLater()
        if chosen is register:
            self.add_favorite()

    def add_favorite(self) -> None:
        if self.current_folder is None:
            return
        folder = str(self.current_folder)
        path = self.files[self.index] if 0 <= self.index < len(self.files) else None
        favorite = Favorite(
            id=uuid.uuid4().hex,
            folder=folder,
            name=self.current_folder.name or folder,
            path=str(path) if path is not None else "",
            thumbnail=encode_thumbnail(self.current_thumbnail()),
        )
        # Registering never replaces an entry: the same folder may be saved again.
        self.favorites = [*self.favorites, favorite]
        self.refresh_favorites()
        self.persist_settings()
        export_favorites_for_widget(self.favorites)
        self.statusBar().showMessage(tr("お気に入りに登録しました: {name}", name=favorite.name), 3000)

    def remove_favorite(self, index: int) -> None:
        if not 0 <= index < len(self.favorites):
            return
        removed = self.favorites[index]
        self.favorites = self.favorites[:index] + self.favorites[index + 1 :]
        if self.favorites_menu.isVisible():
            # Rebuilding would close the open menu; take the row out in place and
            # rebuild once it hides (empty groups, the "no favorites" line).
            self.favorites_menu.drop_entry(index)
            self.favorites_stale = True
        else:
            self.refresh_favorites()
        self.persist_settings()
        export_favorites_for_widget(self.favorites)
        self.statusBar().showMessage(tr("お気に入りから解除しました: {name}", name=removed.name), 3000)

    def move_favorite(self, index: int, group: str) -> None:
        if not 0 <= index < len(self.favorites):
            return
        moved = replace(self.favorites[index], group=group)
        self.favorites = self.favorites[:index] + [moved] + self.favorites[index + 1 :]
        self.refresh_favorites()
        self.persist_settings()
        export_favorites_for_widget(self.favorites)
        where = group or tr("フォルダなし")
        self.statusBar().showMessage(
            tr("{name} を「{group}」へ移動しました", name=moved.name, group=where), 3000
        )

    def name_new_group(self, index: int) -> None:
        if not 0 <= index < len(self.favorites):
            return
        name, accepted = QInputDialog.getText(
            self, tr("新しいフォルダ"), tr("お気に入りをまとめるフォルダ名")
        )
        if accepted and name.strip():
            self.move_favorite(index, name.strip())

    def open_favorite(self, index: int) -> None:
        if not 0 <= index < len(self.favorites):
            return
        favorite = self.favorites[index]
        if favorite.path and Path(favorite.path).is_file():
            self.open_path(Path(favorite.path))
            return
        target = Path(favorite.folder)
        if not target.is_dir():
            QMessageBox.information(
                self,
                tr("フォルダが見つかりません"),
                tr("お気に入りのフォルダが見つかりません。\n{path}", path=target),
            )
            return
        self.open_folder(target, 0)

    def handle_widget_url(self, url: str) -> None:
        """A click on the Mac desktop widget, delivered as our own URL scheme."""
        favorite_id = parse_widget_favorite_id(url)
        if favorite_id is None:
            return
        favorite = resolve_favorite(self.favorites, favorite_id)
        if favorite is None:
            return
        self.open_favorite(self.favorites.index(favorite))
        self.show()
        self.raise_()
        self.activateWindow()

    def handle_opened_file(self, path: str) -> None:
        """A file handed to the app by macOS: double-click, "open with", drag
        onto the dock icon, or a second launch while already running.

        On macOS this arrives only as a QFileOpenEvent (Application.event
        below), never through sys.argv, so main()'s own argv scan alone
        cannot see it.
        """
        self.open_path(Path(path))
        self.show()
        self.raise_()
        self.activateWindow()

    def select_filmstrip_item(self, index: int) -> None:
        if 0 <= index < len(self.files) and index != self.index:
            self.index = index
            self.show_current()

    def render_frame(self) -> None:
        if self.image is None:
            return
        started = perf_counter()
        frame_count = int(getattr(self.image, "n_frames", 1))
        cached = self.animation_cache.get(self.frame_index)
        if cached is not None:
            pixmap, duration, _cost = cached
            self.animation_cache.move_to_end(self.frame_index)
        else:
            self.image.seek(self.frame_index)
            frame = self.image.convert("RGBA")
            if self.spread_second is not None:
                frame = compose_spread(
                    frame,
                    self.spread_second.convert("RGBA"),
                    self.spread_rtl_action.isChecked(),
                )
            values = self.filter_values()
            displayed = frame if values == FilterValues() else apply_filters(frame, values)
            # The effect goes last, so it decides the final look.
            displayed = apply_effect(displayed, self.current_effect(), self.line_color)
            pixmap = QPixmap.fromImage(ImageQt(displayed))
            duration = max(20, int(self.image.info.get("duration", 100)))
            if frame_count > 1:
                self.cache_animation_frame(self.frame_index, pixmap, duration)
        self.image_view.set_pixmap(pixmap, self.pending_pan)
        self.pending_pan = None
        if frame_count > 1:
            elapsed_ms = round((perf_counter() - started) * 1000)
            self.animation_timer.start(max(1, duration - elapsed_ms))

    def cache_animation_frame(self, index: int, pixmap: QPixmap, duration: int) -> None:
        cost = max(1, pixmap.width() * pixmap.height() * 4)
        if cost > self.animation_cache_limit:
            return
        self.animation_cache[index] = (pixmap, duration, cost)
        self.animation_cache_bytes += cost
        while self.animation_cache_bytes > self.animation_cache_limit:
            _old_index, (_old_pixmap, _old_duration, old_cost) = self.animation_cache.popitem(
                last=False
            )
            self.animation_cache_bytes -= old_cost

    def clear_animation_cache(self) -> None:
        self.animation_cache.clear()
        self.animation_cache_bytes = 0

    def advance_animation(self) -> None:
        if self.image is None:
            return
        self.frame_index = (self.frame_index + 1) % int(getattr(self.image, "n_frames", 1))
        self.render_frame()

    def filters_changed(self, _value: int) -> None:
        self.persist_settings()
        self.redraw_current_image()

    def navigate(self, direction: int) -> None:
        if self.folder_prompt_open:
            return
        # Step over the whole view, so a spread turns two pages at a time.
        shown = self.displayed_pages or [self.index]
        target = shown[-1] + 1 if direction > 0 else shown[0] - 1
        if 0 <= target < len(self.files):
            self.index = target
            self.show_current()
            return
        if self.current_folder is None:
            return
        folder = sibling_media_folder(self.current_folder, direction, self.sort_order)
        if folder is None:
            # No neighbouring folder: keep showing the current media instead of warning.
            return
        if direction > 0:
            title, question = "次のフォルダへ移動", "次のフォルダを開きますか？\n{name}"
        else:
            title, question = "前のフォルダへ移動", "前のフォルダを開きますか？\n{name}"
        self.folder_prompt_open = True
        try:
            answer = QMessageBox.question(
                self,
                tr(title),
                tr(question, name=folder.name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        finally:
            self.folder_prompt_open = False
        if answer == QMessageBox.StandardButton.Yes:
            self.open_folder(folder, 0 if direction > 0 else -1)

    def stop_current(self) -> None:
        self.animation_timer.stop()
        self.clear_animation_cache()
        self.player.stop()
        if self.image is not None:
            self.image.close()
            self.image = None
        if self.spread_second is not None:
            self.spread_second.close()
            self.spread_second = None

    def video_error(self, _error: QMediaPlayer.Error, error_string: str) -> None:
        if error_string:
            self.statusBar().showMessage(tr("動画を再生できません: {error}", error=error_string), 8000)

    def toggle_video_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.statusBar().showMessage(tr("一時停止"), 1500)
        else:
            self.player.play()
            self.statusBar().showMessage(tr("再生"), 1500)

    def stop_video(self) -> None:
        """Pause on the first frame rather than QMediaPlayer.stop().

        stop() unloads the picture and leaves the view black, which looks like
        a failed file rather than a stopped one.
        """
        self.player.pause()
        self.seek_video(0)
        self.statusBar().showMessage(tr("停止"), 1500)

    def show_playback_state(self, _state: object = None) -> None:
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_action.setText(tr("❚❚ 一時停止") if playing else tr("▶ 再生"))
        self.play_action.setToolTip(f"{tr('再生／一時停止')} ({tr('動画をクリック')})")

    def set_volume(self, value: int) -> None:
        self.audio.setVolume(value / 100)
        self.volume_slider.setToolTip(f"{tr('音量')}: {value}")
        self.persist_settings()

    def change_volume(self, amount: int) -> None:
        self.volume_slider.setValue(self.volume_slider.value() + amount)

    def seek_video(self, position: int) -> None:
        self.player.setPosition(position)
        self.video_view.update_position(position)

    def persist_settings_soon(self) -> None:
        """Ask for a settings write once the user stops turning pages."""
        if not self.initializing:
            self.settings_timer.start()

    def persist_settings(self) -> None:
        self.settings_timer.stop()
        if self.initializing:
            return
        values = self.filter_values()
        self.settings = ViewerSettings(
            last_path=self.settings.last_path,
            brightness=values.brightness,
            contrast=values.contrast,
            gamma=values.gamma,
            hue=values.hue,
            filter_panel_visible=self.filter_action.isChecked(),
            filmstrip_visible=self.filmstrip_action.isChecked(),
            toolbar_visible=self.toolbar_action.isChecked(),
            status_bar_visible=self.status_bar_action.isChecked(),
            volume=self.volume_slider.value(),
            window_geometry=bytes(self.saveGeometry().toBase64()).decode("ascii"),
            # Still written, so an older copy of the app reads a sensible choice.
            reset_pan_on_change=self.pan_mode() == PAN_TOP,
            pan_mode=self.pan_mode(),
            pan_x=self.fixed_pan[0],
            pan_y=self.fixed_pan[1],
            effect=self.current_effect(),
            line_color=self.line_color,
            spread_view=self.spread_action.isChecked(),
            spread_rtl=self.spread_rtl_action.isChecked(),
            spread_cover=self.spread_cover_action.isChecked(),
            spread_anchor=self.spread_anchor,
            sort_key=self.sort_order.key,
            sort_descending=self.sort_order.descending,
            language=self.language_choice,
            always_on_top=self.always_on_top_action.isChecked(),
            fit_kind=self.image_view.fit_kind,
            slideshow_seconds=self.slideshow_seconds,
            slideshow_effect=self.slideshow_effect,
            slideshow_effect_ms=self.slideshow_effect_ms,
            slideshow_loop=self.slideshow_loop_action.isChecked(),
            slideshow_random=self.slideshow_random_action.isChecked(),
            favorites=list(self.favorites),
        )
        save_settings(self.settings)

    def createPopupMenu(self) -> QMenu | None:
        # QMainWindow offers to hide the toolbar here, and a hidden toolbar cannot
        # be brought back with the mouse, so the offer is withdrawn.
        return None

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.menuBar().setVisible(True)
            self.toolbar.setVisible(self.toolbar_action.isChecked())
            self.statusBar().setVisible(self.status_bar_action.isChecked())
            self.filter_panel.setVisible(self.filter_action.isChecked())
            self.filmstrip.setVisible(self.filmstrip_action.isChecked())
        else:
            self.menuBar().setVisible(False)
            self.toolbar.setVisible(False)
            self.statusBar().setVisible(False)
            self.filter_panel.setVisible(False)
            self.filmstrip.setVisible(False)
            self.showFullScreen()
        self.fullscreen_action.setChecked(self.isFullScreen())

    def toggle_toolbar(self, visible: bool) -> None:
        if not self.isFullScreen():
            self.toolbar.setVisible(visible)
        self.persist_settings()

    def toggle_status_bar(self, visible: bool) -> None:
        if not self.isFullScreen():
            self.statusBar().setVisible(visible)
        self.persist_settings()

    def toggle_filter_panel(self, visible: bool) -> None:
        if not self.isFullScreen():
            self.filter_panel.setVisible(visible)
        self.persist_settings()

    def toggle_filmstrip(self, visible: bool) -> None:
        if not self.isFullScreen():
            self.filmstrip.setVisible(visible)
        self.persist_settings()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
            return
        if event.key() == Qt.Key.Key_F and not self.isFullScreen():
            self.filter_action.toggle()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.open_path(paths[0])
        event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.persist_settings()
        self.slideshow_timer.stop()
        self.filmstrip.loader.close()
        self.stop_current()
        self.preloader.close()
        self.enhancer.close()
        self.ocr_reader.close()
        super().closeEvent(event)


def classify_file_open_event(event: QFileOpenEvent) -> tuple[bool, str]:
    """(is a local file, the path or the URL string) for a QFileOpenEvent.

    QFileOpenEvent.file() is only ever set for an actual file; a custom
    scheme like our own widgetURL only ever populates .url(). Split out from
    Application.event() so it can be tested without a live QApplication,
    which only one of can exist per process.
    """
    path = event.file()
    if path:
        return True, path
    return False, event.url().toString()


class Application(QApplication):
    """Adds the one thing QApplication itself has no signal for.

    On macOS, both opening a file (double-click, "open with", a drag onto
    the dock icon) and activating the app through our own widgetURL scheme
    arrive the same way: a QFileOpenEvent, never through sys.argv, whether
    at cold launch or while already running. Off macOS this event never
    fires, so it costs nothing there.

    At a cold launch this can arrive before anything is connected to
    file_opened / widget_url_opened — macOS can deliver it as soon as
    Qt's Cocoa backend registers its Apple Event handler, which happens
    inside QApplication's own construction, before main() gets to build
    MainWindow and wire the signals up. A signal emitted with no receiver
    is simply dropped, so the event would otherwise be lost and the app
    would fall back to reopening whatever was last on screen. pending_file /
    pending_widget_url latch it so main() can still pick it up afterwards.
    """

    widget_url_opened = Signal(str)
    file_opened = Signal(str)

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.pending_file: str | None = None
        self.pending_widget_url: str | None = None

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FileOpen:
            is_file, value = classify_file_open_event(event)
            if is_file:
                self.pending_file = value
                self.file_opened.emit(value)
            else:
                self.pending_widget_url = value
                self.widget_url_opened.emit(value)
            return True
        return super().event(event)


def main() -> None:
    claim_taskbar_identity()
    app = Application(sys.argv)
    app.setApplicationName("Local Media Viewer")
    app.setWindowIcon(app_icon())
    initial_path = next((Path(argument) for argument in sys.argv[1:] if Path(argument).exists()), None)
    if initial_path is None and app.pending_file is not None:
        initial_path = Path(app.pending_file)
    window = MainWindow(initial_path)
    app.widget_url_opened.connect(window.handle_widget_url)
    app.file_opened.connect(window.handle_opened_file)
    if app.pending_widget_url is not None:
        window.handle_widget_url(app.pending_widget_url)
    window.show()
    raise SystemExit(app.exec())
