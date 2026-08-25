from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor, QPainter, QPixmap
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
    assert view.renderHints() & QPainter.RenderHint.SmoothPixmapTransform

    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton)
    assert view.fit_mode is False
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton)
    assert view.fit_mode is True
    QTest.mouseClick(view.viewport(), Qt.MouseButton.MiddleButton)
    assert fullscreen_requests == [True]
    view.close()


def test_fit_downscales_to_display_pixels_with_lanczos() -> None:
    app = QApplication.instance() or QApplication([])
    view = ImageView()
    view.resize(320, 240)
    source = QPixmap(1200, 800)
    source.fill(Qt.GlobalColor.white)
    view.set_pixmap(source)
    view.show()
    app.processEvents()
    view.fit_to_window()

    assert view.item.pixmap().width() < source.width()
    assert view.item.pixmap().height() < source.height()
    assert view.transform().m11() == 1.0
    assert view.display_scale < 1.0
    view.close()


def test_zoom_upscales_display_pixels_with_bicubic() -> None:
    app = QApplication.instance() or QApplication([])
    view = ImageView()
    source = QPixmap(160, 120)
    source.fill(Qt.GlobalColor.white)
    view.set_pixmap(source)
    view.render_at_scale(2.0)

    assert view.item.pixmap().width() == 320
    assert view.item.pixmap().height() == 240
    assert view.transform().m11() == 1.0
    app.processEvents()
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
    QTest.mouseClick(view.surface, Qt.MouseButton.MiddleButton)
    assert fullscreen_requests == [True]
    QTest.mouseClick(view.surface, Qt.MouseButton.LeftButton)
    assert play_pause_requests == [True]
    view.close()


def test_video_timeline_overlay_shows_and_fades() -> None:
    app = QApplication.instance() or QApplication([])
    view = VideoView()
    view.resize(640, 480)
    seek_requests: list[int] = []
    view.seek_requested.connect(seek_requests.append)
    view.show()
    app.processEvents()
    surface_size_before = view.surface.size()

    view.update_duration(125_000)
    view.update_position(65_000)
    view.show_video_controls()
    assert view.controls.isVisible()
    assert view.surface.size() == surface_size_before
    assert view.controls.time_label.text() == "01:05 / 02:05"
    assert view.controls.time_label.width() == 112
    assert view.controls.time_label.alignment() == Qt.AlignmentFlag.AlignCenter
    assert view.controls.geometry().bottom() <= view.height()
    slider = view.controls.slider
    QTest.mouseClick(
        slider,
        Qt.MouseButton.LeftButton,
        pos=QPoint(slider.width() // 2, slider.height() // 2),
    )
    assert len(seek_requests) >= 1
    assert 60_000 <= seek_requests[-1] <= 65_000
    assert view.controls.time_label.text() == "01:02 / 02:05"

    view.prepare_media()
    assert slider.value() == 0
    assert view.controls.time_label.text() == "00:00 / 00:00"

    view.update_duration(125_000)
    view.update_position(124_800)
    assert slider.value() == 125_000
    assert view.controls.time_label.text() == "02:05 / 02:05"

    slider.setSliderDown(True)
    view.update_position(1_000)
    assert slider.value() == 1_000
    assert view.controls.time_label.text() == "00:01 / 02:05"
    slider.setSliderDown(False)

    view.schedule_controls_hide()
    assert view.controls_hide_timer.interval() == 5000
    assert view.controls_hide_timer.isActive()
    view.controls_hide_timer.stop()
    view.fade_video_controls()
    QTest.qWait(450)
    assert view.controls.isVisible()
    assert view.controls_opacity.opacity() == 0.0
    assert view.surface.size() == surface_size_before
    QCursor.setPos(view.surface.mapToGlobal(QPoint(20, view.surface.height() - 10)))
    view.check_pointer_position()
    assert view.controls.isVisible()
    view.close()
