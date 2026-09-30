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


def test_the_mikan_stands_on_the_m_and_the_m_is_centred() -> None:
    layout = icon_layout()
    size = 512
    image = rendered_icon(size)
    scale = size / 256

    def white(x: int, y: int) -> bool:
        colour = image.pixelColor(x, y)
        return colour.red() > 250 and colour.green() > 250 and colour.blue() > 250

    def yellow(x: int, y: int) -> bool:
        colour = image.pixelColor(x, y)
        return colour.red() > 245 and colour.green() > 215 and colour.blue() < 60

    def lowest(x: float, match) -> int:
        column = round(x * scale)
        return max(y for y in range(size) if match(column, y))

    left_leg = 128 - 78 * layout.M_SCALE + layout.SHIFT_X
    mikan = layout.MIKAN_X + layout.SHIFT_X
    # The fruit's bottom sits on the M's baseline, as the user asked.
    assert abs(lowest(mikan, yellow) - lowest(left_leg, white)) <= 1

    # The M itself sits in the middle of the tile, the fruit sticking out to
    # its right (the user asked for the M back in the centre).
    assert abs((layout.M_LEFT + layout.M_BOX.right()) / 2 + layout.SHIFT_X - 128) < 0.5
    columns = [x for x in range(size) if any(white(x, y) for y in range(0, size, 2))]
    assert abs(columns[0] - layout.M_LEFT * scale) <= 2

    # The fruit stays clear of the tile's edge (4 px here, 2 in the 256 tile).
    # Only opaque pixels count: the tile's softened rim is nearly transparent
    # and its colour values there mean nothing.
    def solid_yellow(x: int, y: int) -> bool:
        return image.pixelColor(x, y).alpha() == 255 and yellow(x, y)

    margin = 4
    for x in range(size):
        for y in list(range(margin)) + list(range(size - margin, size)):
            assert not solid_yellow(x, y) and not solid_yellow(y, x)


def test_the_right_foot_of_the_m_stays_hidden_behind_the_mikan() -> None:
    layout = icon_layout()
    size = 512
    image = rendered_icon(size)
    scale = size / 256
    foot = (layout.M_RIGHT_FOOT.x() + layout.SHIFT_X) * scale
    # The M's right half is 62% white on amber. None of it may show from the
    # fruit's middle down: a sliver there looked like a stray stub of the leg.
    showing = [
        (x, y)
        for x in range(round(foot - 16), round(foot + 16))
        for y in range(round(layout.MIKAN_Y * scale), round((layout.M_BOTTOM + 2) * scale))
        if (colour := image.pixelColor(x, y)).red() > 245
        and 200 < colour.green() < 225
        and 150 < colour.blue() < 185
    ]
    assert showing == []


def test_the_reusable_mikan_files_match_their_source() -> None:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    try:
        import mikan
    finally:
        sys.path.remove(str(root / "scripts"))
    # scripts/mikan.py writes assets/mikan/; a hand edit to either would split them.
    folder = root / "assets" / "mikan"
    assert (folder / "mikan.svg").read_text(encoding="utf-8") == mikan.standalone_svg()
    assert (folder / "mikan-mono.svg").read_text(encoding="utf-8") == mikan.standalone_svg(
        "currentColor"
    )
    # The icon draws the same fruit in the same colour.
    from local_media_viewer.appicon import ICON_SVG

    assert mikan.shapes() in ICON_SVG
    assert mikan.YELLOW in ICON_SVG
