from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path
from time import perf_counter

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QByteArray, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent, QKeyEvent, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QLabel,
    QMainWindow,
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

from local_media_viewer.controls import SnappingSlider
from local_media_viewer.filters import FilterValues, apply_filters
from local_media_viewer.filmstrip import Filmstrip
from local_media_viewer.media import (
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    media_files,
    sibling_media_folder,
)
from local_media_viewer.preloader import ImagePreloader, load_image
from local_media_viewer.settings import ViewerSettings, load_settings, save_settings
from local_media_viewer.viewer import ImageView, VideoView


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
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

        self.setWindowTitle("Local Media Viewer")
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        self.image_view = ImageView()
        self.video_view = VideoView()
        self.image_view.navigate.connect(self.navigate)
        self.video_view.navigate.connect(self.navigate)
        self.video_view.play_pause_requested.connect(self.toggle_video_playback)
        self.video_view.volume_change_requested.connect(self.change_volume)
        self.image_view.fullscreen_requested.connect(self.toggle_fullscreen)
        self.video_view.fullscreen_requested.connect(self.toggle_fullscreen)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.image_view)
        self.stack.addWidget(self.video_view)

        self.audio = QAudioOutput(self)
        self.audio.setVolume(self.settings.volume / 100)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_view)
        self.player.errorOccurred.connect(self.video_error)

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
        self.restore_state()

    def create_toolbar(self) -> None:
        self.toolbar = QToolBar("操作")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        open_file = QAction("ファイルを開く", self)
        open_folder = QAction("フォルダを開く", self)
        previous = QAction("前へ", self)
        next_item = QAction("次へ", self)
        fit = QAction("フィット／原寸", self)
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
        self.toolbar.addWidget(QLabel("音量"))
        self.toolbar.addWidget(self.volume_slider)
        self.toggle_filter_panel(self.settings.filter_panel_visible)
        self.toggle_filmstrip(self.settings.filmstrip_visible)

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

    def restore_state(self) -> None:
        if self.settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.settings.window_geometry.encode("ascii")))
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

    def show_current(self) -> None:
        if not (0 <= self.index < len(self.files)):
            return
        path = self.files[self.index]
        self.filmstrip.set_files(self.files)
        self.filmstrip.set_current(self.index)
        self.stop_current()
        self.setWindowTitle(f"{path.name} — Local Media Viewer")
        self.statusBar().showMessage(f"{self.index + 1} / {len(self.files)}　{path}")
        self.settings.last_path = str(path)
        self.persist_settings()
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            self.stack.setCurrentWidget(self.video_view)
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.play()
        else:
            self.stack.setCurrentWidget(self.image_view)
            try:
                self.image = self.preloader.take(path) or load_image(path)
                self.frame_index = 0
                self.render_frame()
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "画像を開けません", f"{path.name}\n{error}")
        self.preload_nearby_images()

    def preload_nearby_images(self) -> None:
        nearby: list[Path] = []
        for distance in range(1, 4):
            for target in (self.index + distance, self.index - distance):
                if 0 <= target < len(self.files):
                    path = self.files[target]
                    if path.suffix.lower() in IMAGE_EXTENSIONS:
                        nearby.append(path)
        self.preloader.preload(nearby)

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
            values = self.filter_values()
            displayed = frame if values == FilterValues() else apply_filters(frame, values)
            pixmap = QPixmap.fromImage(ImageQt(displayed))
            duration = max(20, int(self.image.info.get("duration", 100)))
            if frame_count > 1:
                self.cache_animation_frame(self.frame_index, pixmap, duration)
        self.image_view.set_pixmap(pixmap)
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
        target = self.index + direction
        if 0 <= target < len(self.files):
            self.index = target
            self.show_current()
            return
        if self.current_folder is None:
            return
        folder = sibling_media_folder(self.current_folder, direction)
        if folder is None:
            label = "次" if direction > 0 else "前"
            QMessageBox.information(
                self,
                f"{label}のフォルダなし",
                f"{label}方向に表示できる画像・動画を含むフォルダがありません。",
            )
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

    def persist_settings(self) -> None:
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
        )
        save_settings(self.settings)

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
    app = QApplication(sys.argv)
    app.setApplicationName("Local Media Viewer")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
