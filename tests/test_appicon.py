from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer.appicon import ICON_SIZES, app_icon, claim_taskbar_identity
from local_media_viewer.settings import ViewerSettings


def test_the_icon_carries_every_size_it_advertises() -> None:
    QApplication.instance() or QApplication([])
    icon = app_icon()

    assert not icon.isNull()
    assert {(s.width(), s.height()) for s in icon.availableSizes()} == {
        (size, size) for size in ICON_SIZES
    }
    # The mark is white on amber, so the centre of the tile must not be blank.
    small = icon.pixmap(32, 32)
    assert small.width() == 32
    assert small.toImage().pixelColor(16, 16).alpha() == 255


def test_the_window_wears_the_icon(monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    window = app_module.MainWindow()
    try:
        # Without this the title bar falls back to Qt's default icon.
        assert not window.windowIcon().isNull()
        assert window.windowIcon().availableSizes()
    finally:
        window.close()


def test_claiming_the_taskbar_identity_is_safe_to_call() -> None:
    claim_taskbar_identity()
    claim_taskbar_identity()


def test_the_embedded_icon_matches_the_asset() -> None:
    from pathlib import Path

    from local_media_viewer.appicon import ICON_SVG

    # scripts/make_icon.py writes both; a hand edit to one would split them.
    asset = Path(__file__).resolve().parents[1] / "assets" / "icon.svg"
    assert ICON_SVG == asset.read_text(encoding="utf-8")


def test_the_arms_of_the_m_meet_in_one_solid_joint() -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    from local_media_viewer.appicon import ICON_SVG

    QApplication.instance() or QApplication([])
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(ICON_SVG.encode("utf-8")).render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    # Just above where the arms meet. The old icon drew two separate strokes
    # whose round ends barely touched, leaving the amber showing through here.
    joint = image.pixelColor(128, 140)
    assert joint.green() > 200 and joint.blue() > 150, joint.name()
    # Either side of the centre, the halves keep their two tones.
    assert image.pixelColor(122, 140).name() == "#ffffff"
    assert image.pixelColor(134, 140).name() != "#ffffff"
