from pathlib import Path

from PIL import Image
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.settings import ViewerSettings


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def media_folder(tmp_path: Path) -> Path:
    Image.new("RGB", (16, 12), "red").save(tmp_path / "a.png")
    # Never decoded successfully; only the extension decides the view.
    (tmp_path / "b.mp4").write_bytes(b"not a real video")
    return tmp_path


def test_video_controls_show_only_for_videos(tmp_path: Path, monkeypatch) -> None:
    folder = media_folder(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = make_window(monkeypatch)
    try:
        window.show()
        app.processEvents()
        # Nothing open yet: nothing to play.
        assert not window.volume_slider.isVisible()

        window.open_path(folder / "a.png")
        app.processEvents()
        assert not window.volume_slider.isVisible()
        assert not window.play_action.isVisible()

        window.open_path(folder / "b.mp4")
        app.processEvents()
        assert window.volume_slider.isVisible()
        assert window.volume_label.isVisible()
        assert all(
            action.isVisible()
            for action in (window.play_action, window.stop_action, window.mute_action)
        )

        window.navigate(-1)
        app.processEvents()
        assert not window.volume_slider.isVisible()
    finally:
        window.close()


def test_play_button_names_what_it_will_do(monkeypatch) -> None:
    window = make_window(monkeypatch)
    state = {"value": QMediaPlayer.PlaybackState.StoppedState}
    monkeypatch.setattr(window.player, "playbackState", lambda: state["value"])
    try:
        window.show_playback_state()
        assert window.play_action.text() == "▶ 再生"
        state["value"] = QMediaPlayer.PlaybackState.PlayingState
        window.show_playback_state()
        assert window.play_action.text() == "❚❚ 一時停止"
    finally:
        window.close()


def test_stop_pauses_on_the_first_frame(monkeypatch) -> None:
    window = make_window(monkeypatch)
    calls: list = []
    monkeypatch.setattr(window.player, "pause", lambda: calls.append("pause"))
    monkeypatch.setattr(window.player, "setPosition", lambda value: calls.append(value))
    try:
        window.stop_video()
        assert calls == ["pause", 0]
    finally:
        window.close()


def test_mute_silences_without_moving_the_volume(monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        before = window.volume_slider.value()
        window.mute_action.setChecked(True)
        assert window.audio.isMuted()
        assert window.volume_slider.value() == before
        window.mute_action.setChecked(False)
        assert not window.audio.isMuted()
    finally:
        window.close()


def test_right_click_offers_playback_only_on_a_video(tmp_path: Path, monkeypatch) -> None:
    folder = media_folder(tmp_path)
    shown: list[list] = []

    class RecordingMenu(app_module.QMenu):
        def exec(self, *_args):
            shown.append(self.actions())
            return None

    window = make_window(monkeypatch)
    monkeypatch.setattr(app_module, "QMenu", RecordingMenu)
    try:
        window.open_path(folder / "a.png")
        window.show_media_menu(window.pos())
        assert window.play_action not in shown[-1]

        window.open_path(folder / "b.mp4")
        window.show_media_menu(window.pos())
        assert window.play_action in shown[-1]
        assert window.stop_action in shown[-1]
    finally:
        window.close()
