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


def icon_layout():
    """scripts/make_icon.py, loaded for the geometry it lays the icon out by."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "make_icon.py"
    spec = importlib.util.spec_from_file_location("make_icon", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered_icon(size: int):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    from local_media_viewer.appicon import ICON_SVG

    QApplication.instance() or QApplication([])
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(ICON_SVG.encode("utf-8")).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def test_the_arms_of_the_m_meet_in_one_solid_joint() -> None:
    layout = icon_layout()
    image = rendered_icon(256)
    # The mark is shifted left to make room for the mikan beside it.
    centre = round(128 + layout.SHIFT_X)
    # Just above where the arms meet. The old icon drew two separate strokes
    # whose round ends barely touched, leaving the amber showing through here.
    joint = image.pixelColor(centre, 140)
    assert joint.green() > 200 and joint.blue() > 150, joint.name()
    # Either side of the centre, the halves keep their two tones.
    assert image.pixelColor(centre - 6, 140).name() == "#ffffff"
    assert image.pixelColor(centre + 6, 140).name() != "#ffffff"


def test_the_mikan_stands_on_the_m_and_the_pair_is_centred() -> None:
    layout = icon_layout()
    size = 512
    image = rendered_icon(size)
    scale = size / 256

    def white(x: int, y: int) -> bool:
        colour = image.pixelColor(x, y)
        return colour.red() > 250 and colour.green() > 250 and colour.blue() > 250

    def lowest_white(x: float) -> int:
        column = round(x * scale)
        return max(y for y in range(size) if white(column, y))

    left_leg = 128 - 78 * layout.M_SCALE + layout.SHIFT_X
    mikan = layout.MIKAN_X + layout.SHIFT_X
    # The fruit's bottom sits on the M's baseline, as the user asked.
    assert abs(lowest_white(mikan) - lowest_white(left_leg)) <= 1

    # The M and the fruit together sit in the middle of the tile.
    columns = [x for x in range(size) if any(white(x, y) for y in range(0, size, 2))]
    assert abs(columns[0] - (size - 1 - columns[-1])) <= 2
