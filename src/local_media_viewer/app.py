from __future__ import annotations

import sys
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QByteArray, QPoint, QTimer, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeyEvent,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from local_media_viewer.appicon import app_icon, claim_taskbar_identity
from local_media_viewer.controls import SnappingSlider
from local_media_viewer.favorites import FavoritesMenu, encode_thumbnail
from local_media_viewer.filters import FilterValues, apply_filters
from local_media_viewer.filmstrip import Filmstrip
from local_media_viewer.media import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    media_files,
    sibling_media_folder,
)
from local_media_viewer.preloader import ImagePreloader, load_image
from local_media_viewer.settings import (
    Favorite,
    ViewerSettings,
    load_settings,
    save_settings,
)
from local_media_viewer.spread import compose_spread, is_animated
from local_media_viewer.viewer import ImageView, VideoView


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
        self.folder_prompt_open = False
        self.favorites: list[Favorite] = list(self.settings.favorites)
        self.spread_second: Image.Image | None = None
        self.spread_anchor = max(0, self.settings.spread_anchor)
        self.displayed_pages: list[int] = []
        self.pending_pan_reset = False

        self.setWindowTitle("Local Media Viewer")
        self.setWindowIcon(app_icon())
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self.image_view = ImageView()
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
        self.create_toolbar()
        self.restore_state(initial_path)
        self.initializing = False

    def create_toolbar(self) -> None:
        self.toolbar = QToolBar("操作")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        open_file = QAction("ファイルを開く", self)
        open_folder = QAction("フォルダを開く", self)
        previous = QAction("前へ", self)
        next_item = QAction("次へ", self)
        previous.setShortcuts(
            [
                QKeySequence(Qt.Key.Key_Left),
                QKeySequence(Qt.Key.Key_Up),
            ]
        )
        next_item.setShortcuts(
            [
                QKeySequence(Qt.Key.Key_Right),
                QKeySequence(Qt.Key.Key_Down),
            ]
        )
        previous.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        next_item.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        previous.setToolTip("前へ (← / ↑)")
        next_item.setToolTip("次へ (→ / ↓)")
        fit = QAction("フィット／原寸", self)
        fit.setShortcut(QKeySequence(Qt.Key.Key_Space))
        fit.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        fit.setToolTip("フィット／原寸 (Space)")
        open_file.triggered.connect(self.choose_file)
        open_folder.triggered.connect(self.choose_folder)
        previous.triggered.connect(lambda: self.navigate(-1))
        next_item.triggered.connect(lambda: self.navigate(1))
        fit.triggered.connect(self.image_view.toggle_fit)
        self.filter_action = QAction("フィルター", self)
        self.filter_action.setCheckable(True)
        self.filter_action.setChecked(self.settings.filter_panel_visible)
        self.filter_action.toggled.connect(self.toggle_filter_panel)
        self.filmstrip_action = QAction("フィルムストリップ", self)
        self.filmstrip_action.setCheckable(True)
        self.filmstrip_action.setChecked(self.settings.filmstrip_visible)
        self.filmstrip_action.toggled.connect(self.toggle_filmstrip)
        self.option_actions = self.create_option_actions()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.settings.volume)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.setToolTip(f"音量: {self.settings.volume}")
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.toolbar.addActions([open_file, open_folder, previous, next_item, fit])
        self.toolbar.addSeparator()
        self.toolbar.addActions([self.filter_action, self.filmstrip_action])
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.create_favorites_button())
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("音量"))
        self.toolbar.addWidget(self.volume_slider)
        self.fullscreen_shortcuts = [
            QShortcut(QKeySequence(Qt.Key.Key_Return), self),
            QShortcut(QKeySequence(Qt.Key.Key_Enter), self),
        ]
        for shortcut in self.fullscreen_shortcuts:
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(self.toggle_fullscreen)
        self.refresh_favorites()
        self.toggle_filter_panel(self.settings.filter_panel_visible)
        self.toggle_filmstrip(self.settings.filmstrip_visible)

    def create_option_actions(self) -> list[QAction]:
        """Checkable settings shared by the favorites menu and the right-click menu."""
        self.reset_pan_action = QAction("次の画像で表示位置を戻す", self)
        self.reset_pan_action.setCheckable(True)
        self.reset_pan_action.setChecked(self.settings.reset_pan_on_change)
        self.reset_pan_action.toggled.connect(self.change_reset_pan)
        self.spread_action = QAction("見開き表示（2ページ）", self)
        self.spread_action.setCheckable(True)
        self.spread_action.setChecked(self.settings.spread_view)
        self.spread_action.toggled.connect(self.toggle_spread)
        self.spread_rtl_action = QAction("見開きを右送りにする", self)
        self.spread_rtl_action.setCheckable(True)
        self.spread_rtl_action.setChecked(self.settings.spread_rtl)
        self.spread_rtl_action.toggled.connect(self.change_spread_direction)
        self.spread_here_action = QAction("このページから見開きを開始", self)
        self.spread_here_action.triggered.connect(self.start_spread_here)
        return [
            self.filmstrip_action,
            self.filter_action,
            self.reset_pan_action,
            self.spread_action,
            self.spread_rtl_action,
            self.spread_here_action,
        ]

    def change_reset_pan(self, _enabled: bool) -> None:
        self.persist_settings()

    def toggle_spread(self, enabled: bool) -> None:
        if enabled:
            # The page it was switched on at becomes the first half of the spread.
            self.spread_anchor = max(0, self.index)
        self.persist_settings()
        self.show_current()

    def change_spread_direction(self, _right_to_left: bool) -> None:
        self.persist_settings()
        self.show_current()

    def start_spread_here(self) -> None:
        self.spread_anchor = max(0, self.index)
        if not self.spread_action.isChecked():
            self.spread_action.setChecked(True)  # toggle_spread redraws
            return
        self.persist_settings()
        self.show_current()

    def create_filter_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        title = QLabel("表示フィルター")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        note = QLabel("元ファイルは変更されません")
        note.setStyleSheet("color: #667085;")
        layout.addWidget(title)
        layout.addWidget(note)
        form = QFormLayout()
        self.brightness = self.make_slider(-100, 100, self.settings.brightness, 0)
        self.contrast = self.make_slider(-100, 100, self.settings.contrast, 0)
        self.gamma = self.make_slider(
            20, 300, round(self.settings.gamma * 100), 100, divisions=14
        )
        self.hue = self.make_slider(-180, 180, self.settings.hue, 0)
        form.addRow("明るさ", self.brightness)
        form.addRow("コントラスト", self.contrast)
        form.addRow("ガンマ", self.gamma)
        form.addRow("色相", self.hue)
        layout.addLayout(form)
        reset = QPushButton("フィルターをリセット")
        reset.clicked.connect(self.reset_filters)
        layout.addWidget(reset)
        self.video_filter_note = QLabel("動画には初期版では適用されません")
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
        selected, _ = QFileDialog.getOpenFileName(self, "画像・動画を開く", start, "Media files (*)")
        if selected:
            self.open_path(Path(selected))

    def choose_folder(self) -> None:
        start = str(self.current_folder or Path.home())
        selected = QFileDialog.getExistingDirectory(self, "フォルダを開く", start)
        if selected:
            self.open_folder(Path(selected), 0)

    def open_path(self, path: Path) -> None:
        if path.is_dir():
            self.open_folder(path, 0)
            return
        files = media_files(path.parent)
        if path not in files:
            QMessageBox.warning(self, "非対応形式", f"対応していないファイルです。\n{path.name}")
            return
        self.current_folder = path.parent
        self.files = files
        self.index = files.index(path)
        self.show_current()

    def open_folder(self, folder: Path, index: int) -> None:
        files = media_files(folder)
        if not files:
            QMessageBox.information(self, "メディアなし", f"対応ファイルがありません。\n{folder}")
            return
        self.current_folder = folder
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
        try:
            with Image.open(path) as probe:
                return not is_animated(probe)
        except (OSError, ValueError):
            return False

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
            self.spread_second = self.preloader.take(path) or load_image(path)
        except (OSError, ValueError):
            self.spread_second = None

    def show_current(self) -> None:
        if not (0 <= self.index < len(self.files)):
            return
        pages = self.spread_pages()
        self.index = pages[0]
        path = self.files[self.index]
        self.filmstrip.set_files(self.files)
        self.filmstrip.set_current(self.index)
        self.stop_current()
        self.setWindowTitle(f"{path.name} — Local Media Viewer")
        self.settings.last_path = str(path)
        self.persist_settings()
        self.displayed_pages = [self.index]
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            self.stack.setCurrentWidget(self.video_view)
            self.video_view.prepare_media()
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.play()
            self.video_view.activate_controls()
        else:
            self.stack.setCurrentWidget(self.image_view)
            self.video_view.update_duration(0)
            try:
                self.image = self.preloader.take(path) or load_image(path)
                if len(pages) > 1:
                    self.load_second_page(pages[1])
                    # Keep the pair as the step unit even if the partner
                    # failed to load, so paging cannot stall on it.
                    self.displayed_pages = pages
                self.frame_index = 0
                self.pending_pan_reset = self.reset_pan_action.isChecked()
                self.render_frame()
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "画像を開けません", f"{path.name}\n{error}")
        self.show_page_status()
        self.preload_nearby_images()

    def show_page_status(self) -> None:
        pages = self.displayed_pages or [self.index]
        numbers = "-".join(str(page + 1) for page in pages)
        self.statusBar().showMessage(
            f"{numbers} / {len(self.files)}　{self.files[pages[0]]}"
        )

    def preload_nearby_images(self) -> None:
        nearby: list[Path] = []
        for distance in range(1, 4):
            for target in (self.index + distance, self.index - distance):
                if 0 <= target < len(self.files):
                    path = self.files[target]
                    if path.suffix.lower() in IMAGE_EXTENSIONS:
                        nearby.append(path)
        self.preloader.preload(nearby)

    def create_favorites_button(self) -> QToolButton:
        self.favorites_menu = FavoritesMenu()
        self.favorites_menu.activated.connect(self.open_favorite)
        self.favorites_menu.remove_requested.connect(self.remove_favorite)
        self.favorites_menu.move_requested.connect(self.move_favorite)
        self.favorites_menu.new_group_requested.connect(self.name_new_group)
        self.favorites_button = QToolButton()
        # A plain text button that drops its own menu: attaching the menu to the
        # button instead makes the style paint a stray arrow beside the label.
        self.favorites_button.setText("お気に入り ▾")
        self.favorites_button.setToolTip("登録したお気に入りを開く")
        self.favorites_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.favorites_button.setAutoRaise(True)
        self.favorites_button.clicked.connect(self.show_favorites_menu)
        return self.favorites_button

    def show_favorites_menu(self) -> None:
        button = self.favorites_button
        corner = button.mapToGlobal(QPoint(0, button.height()))
        # Trim the popup to the room under the label, so Qt never lifts it
        # back over the toolbar to make it fit.
        self.favorites_menu.limit_to(button.screen().availableGeometry().bottom() - corner.y())
        self.favorites_menu.popup(corner)
        if self.favorites_menu.pos() != corner:
            # Qt places the popup from its unconstrained size hint, which lifts a
            # long list off the label; the trimmed menu does fit, so put it back.
            self.favorites_menu.move(corner)

    def refresh_favorites(self) -> None:
        self.favorites_menu.set_favorites(self.favorites, self.option_actions)

    def current_thumbnail(self) -> QPixmap:
        if self.stack.currentWidget() is self.video_view:
            return self.video_view.frame_pixmap()
        return self.image_view.source_pixmap

    def show_media_menu(self, position: QPoint) -> None:
        if self.current_folder is None:
            return
        menu = QMenu(self)
        register = menu.addAction("お気に入りに登録")
        menu.addSeparator()
        menu.addActions(self.option_actions)
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
            folder=folder,
            name=self.current_folder.name or folder,
            path=str(path) if path is not None else "",
            thumbnail=encode_thumbnail(self.current_thumbnail()),
        )
        # Registering never replaces an entry: the same folder may be saved again.
        self.favorites = [*self.favorites, favorite]
        self.refresh_favorites()
        self.persist_settings()
        self.statusBar().showMessage(f"お気に入りに登録しました: {favorite.name}", 3000)

    def remove_favorite(self, index: int) -> None:
        if not 0 <= index < len(self.favorites):
            return
        removed = self.favorites[index]
        self.favorites = self.favorites[:index] + self.favorites[index + 1 :]
        self.refresh_favorites()
        self.persist_settings()
        self.statusBar().showMessage(f"お気に入りから解除しました: {removed.name}", 3000)

    def move_favorite(self, index: int, group: str) -> None:
        if not 0 <= index < len(self.favorites):
            return
        moved = replace(self.favorites[index], group=group)
        self.favorites = self.favorites[:index] + [moved] + self.favorites[index + 1 :]
        self.refresh_favorites()
        self.persist_settings()
        where = group or "フォルダなし"
        self.statusBar().showMessage(f"{moved.name} を「{where}」へ移動しました", 3000)

    def name_new_group(self, index: int) -> None:
        if not 0 <= index < len(self.favorites):
            return
        name, accepted = QInputDialog.getText(
            self, "新しいフォルダ", "お気に入りをまとめるフォルダ名"
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
                "フォルダなし",
                f"お気に入りのフォルダが見つかりません。\n{folder}",
            )
            return
        self.open_folder(target, 0)

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
            pixmap = QPixmap.fromImage(ImageQt(displayed))
            duration = max(20, int(self.image.info.get("duration", 100)))
            if frame_count > 1:
                self.cache_animation_frame(self.frame_index, pixmap, duration)
        self.image_view.set_pixmap(pixmap, self.pending_pan_reset)
        self.pending_pan_reset = False
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
        if self.stack.currentWidget() is self.image_view and self.image is not None:
            self.clear_animation_cache()
            self.render_frame()

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
        folder = sibling_media_folder(self.current_folder, direction)
        if folder is None:
            # No neighbouring folder: keep showing the current media instead of warning.
            return
        label = "次" if direction > 0 else "前"
        self.folder_prompt_open = True
        try:
            answer = QMessageBox.question(
                self,
                f"{label}のフォルダへ移動",
                f"{label}のフォルダを開きますか？\n{folder.name}",
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
            self.statusBar().showMessage(f"動画を再生できません: {error_string}", 8000)

    def toggle_video_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.statusBar().showMessage("一時停止", 1500)
        else:
            self.player.play()
            self.statusBar().showMessage("再生", 1500)

    def set_volume(self, value: int) -> None:
        self.audio.setVolume(value / 100)
        self.volume_slider.setToolTip(f"音量: {value}")
        self.persist_settings()

    def change_volume(self, amount: int) -> None:
        self.volume_slider.setValue(self.volume_slider.value() + amount)

    def seek_video(self, position: int) -> None:
        self.player.setPosition(position)
        self.video_view.update_position(position)

    def persist_settings(self) -> None:
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
            volume=self.volume_slider.value(),
            window_geometry=bytes(self.saveGeometry().toBase64()).decode("ascii"),
            reset_pan_on_change=self.reset_pan_action.isChecked(),
            spread_view=self.spread_action.isChecked(),
            spread_rtl=self.spread_rtl_action.isChecked(),
            spread_anchor=self.spread_anchor,
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
            self.toolbar.setVisible(True)
            self.statusBar().setVisible(True)
            self.filter_panel.setVisible(self.filter_action.isChecked())
            self.filmstrip.setVisible(self.filmstrip_action.isChecked())
        else:
            self.toolbar.setVisible(False)
            self.statusBar().setVisible(False)
            self.filter_panel.setVisible(False)
            self.filmstrip.setVisible(False)
            self.showFullScreen()

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
        self.stop_current()
        self.preloader.close()
        super().closeEvent(event)


def main() -> None:
    claim_taskbar_identity()
    app = QApplication(sys.argv)
    app.setApplicationName("Local Media Viewer")
    app.setWindowIcon(app_icon())
    initial_path = next((Path(argument) for argument in sys.argv[1:] if Path(argument).exists()), None)
    window = MainWindow(initial_path)
    window.show()
    raise SystemExit(app.exec())
