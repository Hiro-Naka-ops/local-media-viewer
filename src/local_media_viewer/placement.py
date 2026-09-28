"""Where the window goes for the ウィンドウ menu's placement commands.

Pure rectangle arithmetic on the work area (the screen minus the taskbar), so
it can be tested without showing a window. Every rectangle here is an outer
frame; the window turns it into client geometry itself.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize

LEFT = "left"
RIGHT = "right"


def half(area: QRect, side: str) -> QRect:
    """The left or right half of a work area; the right takes any odd pixel."""
    left_width = area.width() // 2
    if side == LEFT:
        return QRect(area.x(), area.y(), left_width, area.height())
    return QRect(area.x() + left_width, area.y(), area.width() - left_width, area.height())


def centered(area: QRect, size: QSize) -> QRect:
    """A frame of the given size in the middle of the area, shrunk if it cannot fit."""
    width = min(size.width(), area.width())
    height = min(size.height(), area.height())
    return QRect(
        area.x() + (area.width() - width) // 2,
        area.y() + (area.height() - height) // 2,
        width,
        height,
    )


def carried_over(frame: QRect, source: QRect, target: QRect) -> QRect:
    """The same frame on another screen, at the same relative place and size.

    Screens differ in size, so the frame is scaled with the work area rather
    than moved by a fixed offset, which could leave it hanging off a smaller
    display or tiny on a bigger one.
    """
    if source.width() <= 0 or source.height() <= 0:
        return centered(target, frame.size())
    scale_x = target.width() / source.width()
    scale_y = target.height() / source.height()
    width = min(round(frame.width() * scale_x), target.width())
    height = min(round(frame.height() * scale_y), target.height())
    x = target.x() + round((frame.x() - source.x()) * scale_x)
    y = target.y() + round((frame.y() - source.y()) * scale_y)
    # Keep the whole frame on the new screen, title bar included.
    x = max(target.x(), min(x, target.x() + target.width() - width))
    y = max(target.y(), min(y, target.y() + target.height() - height))
    return QRect(x, y, width, height)
