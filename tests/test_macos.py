import importlib
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QFileOpenEvent, QWheelEvent

from local_media_viewer import appicon, settings
from local_media_viewer.app import classify_file_open_event
from local_media_viewer.viewer import SWIPE_DISTANCE, WheelPager


def swipe_event(phase: Qt.ScrollPhase, dy: int = 0, dx: int = 0) -> QWheelEvent:
    # A trackpad reports pixels, and Qt fills the angle delta from them too.
    return QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(dx, dy),
        QPoint(dx, dy),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        phase,
        False,
    )


def swipe(pager: WheelPager, dy: int = 0, dx: int = 0, events: int = 20) -> list[int]:
    """One full gesture: begin, many small moves, lift, then momentum."""
    steps = [pager.step(swipe_event(Qt.ScrollPhase.ScrollBegin))]
    steps += [pager.step(swipe_event(Qt.ScrollPhase.ScrollUpdate, dy, dx)) for _ in range(events)]
    steps.append(pager.step(swipe_event(Qt.ScrollPhase.ScrollEnd)))
    steps += [pager.step(swipe_event(Qt.ScrollPhase.ScrollMomentum, dy, dx)) for _ in range(30)]
    return [step for step in steps if step]


def test_a_trackpad_swipe_turns_exactly_one_page() -> None:
    pager = WheelPager()
    assert swipe(pager, dy=-8) == [1]
    assert swipe(pager, dy=8) == [-1]
    # Sideways works like the tilt wheel: right is forward.
    assert swipe(pager, dx=8) == [1]


def test_a_tiny_brush_of_the_trackpad_turns_nothing() -> None:
    pager = WheelPager()
    assert swipe(pager, dy=-1, events=SWIPE_DISTANCE - 1) == []


def test_a_mouse_wheel_still_turns_a_page_per_notch() -> None:
    pager = WheelPager()
    notch = swipe_event(Qt.ScrollPhase.NoScrollPhase, dy=-120)
    assert [pager.step(notch) for _ in range(3)] == [1, 1, 1]


def test_settings_live_in_application_support_on_macos(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    path = settings.settings_path()
    assert path.parts[-4:] == ("Library", "Application Support", "LocalMediaViewer", "settings.json")
    assert path.is_relative_to(Path.home())


def test_the_icon_module_loads_without_windll(monkeypatch) -> None:
    import ctypes

    # macOS has no ctypes.windll; importing the module must not reach for it.
    monkeypatch.delattr(ctypes, "windll", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    try:
        module = importlib.reload(appicon)
        module.claim_taskbar_identity()  # a no-op off Windows
    finally:
        monkeypatch.undo()
        importlib.reload(appicon)


def test_a_file_opened_via_finder_is_classified_as_a_file() -> None:
    # Double-click, "open with", drag onto the dock icon: QFileOpenEvent.file()
    # is set. Must be routed to open_path, not mistaken for a widgetURL.
    event = QFileOpenEvent(QUrl.fromLocalFile("/pictures/スクリーンショット 2026-09-30.png"))
    is_file, value = classify_file_open_event(event)
    assert is_file is True
    assert value == "/pictures/スクリーンショット 2026-09-30.png"


def test_the_widget_url_scheme_is_classified_as_a_url_not_a_file() -> None:
    # The Mac widget's own scheme: file() is empty, only url() is meaningful.
    event = QFileOpenEvent(QUrl("localmediaviewer://favorite?id=abc123"))
    is_file, value = classify_file_open_event(event)
    assert is_file is False
    assert value == "localmediaviewer://favorite?id=abc123"
