from __future__ import annotations

import re
import sys
from ctypes import windll
from functools import cmp_to_key
from pathlib import Path
from typing import Iterable

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def windows_name_compare(left: Path, right: Path) -> int:
    return int(windll.shlwapi.StrCmpLogicalW(left.name, right.name))


def name_sorted(paths: Iterable[Path]) -> list[Path]:
    items = list(paths)
    if sys.platform == "win32":
        return sorted(items, key=cmp_to_key(windows_name_compare))
    return sorted(items, key=natural_key)


def media_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return name_sorted(
        item
        for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() in MEDIA_EXTENSIONS
    )


def sibling_folder(current: Path, direction: int) -> Path | None:
    parent = current.parent
    siblings = name_sorted(item for item in parent.iterdir() if item.is_dir())
    try:
        index = siblings.index(current)
    except ValueError:
        return None
    target = index + direction
    return siblings[target] if 0 <= target < len(siblings) else None


def sibling_media_folder(current: Path, direction: int) -> Path | None:
    """Find the next sibling folder that actually contains supported media."""
    candidate = sibling_folder(current, direction)
    while candidate is not None:
        if media_files(candidate):
            return candidate
        candidate = sibling_folder(candidate, direction)
    return None
