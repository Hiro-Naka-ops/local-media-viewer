from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.settings import ViewerSettings


def test_animated_webp_frames_are_cached(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "animated.webp"
    frames = [
        Image.new("RGB", (24, 16), color)
        for color in ("red", "green", "blue")
    ]
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=[40, 60, 80],
        loop=0,
        lossless=True,
    )
    qt_app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    window = app_module.MainWindow()
    try:
        window.open_path(path)
        window.animation_timer.stop()
        for index in range(3):
            window.frame_index = index
            window.render_frame()
            window.animation_timer.stop()
        assert len(window.animation_cache) == 3
        assert [item[1] for item in window.animation_cache.values()] == [40, 60, 80]
        qt_app.processEvents()
    finally:
        window.close()
