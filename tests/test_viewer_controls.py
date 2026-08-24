from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from local_media_viewer.viewer import ImageView, VideoView


def test_image_click_controls() -> None:
    app = QApplication.instance() or QApplication([])
    view = ImageView()
    view.resize(320, 240)
    view.set_pixmap(QPixmap(100, 80))
    fullscreen_requests: list[bool] = []
    view.fullscreen_requested.connect(lambda: fullscreen_requests.append(True))
    view.show()
    app.processEvents()

    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton)
    assert view.fit_mode is False
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton)
    assert view.fit_mode is True
    QTest.mouseClick(view.viewport(), Qt.MouseButton.MiddleButton)
    assert fullscreen_requests == [True]
    view.close()


def test_video_middle_click_requests_fullscreen() -> None:
    app = QApplication.instance() or QApplication([])
    view = VideoView()
    fullscreen_requests: list[bool] = []
    play_pause_requests: list[bool] = []
    view.fullscreen_requested.connect(lambda: fullscreen_requests.append(True))
    view.play_pause_requested.connect(lambda: play_pause_requests.append(True))
    view.show()
    app.processEvents()
    QTest.mouseClick(view, Qt.MouseButton.MiddleButton)
    assert fullscreen_requests == [True]
    QTest.mouseClick(view, Qt.MouseButton.LeftButton)
    assert play_pause_requests == [True]
    view.close()
