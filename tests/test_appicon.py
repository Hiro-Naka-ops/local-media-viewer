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
