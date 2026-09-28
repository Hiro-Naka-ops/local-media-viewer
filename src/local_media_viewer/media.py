from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from functools import cmp_to_key
from pathlib import Path
from typing import Iterable, Iterator

# HEIC / HEIF (iPhone photos) are decoded by pillow-heif; see preloader.py.
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".heic", ".heif"
}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

SORT_NAME = "name"
SORT_CREATED = "created"
SORT_MODIFIED = "modified"

# Shown in the 並び順 submenu, in this order. The labels are i18n keys.
SORT_LABELS: list[tuple[str, str]] = [
    (SORT_NAME, "ファイル・フォルダ名"),
    (SORT_CREATED, "作成日時"),
    (SORT_MODIFIED, "更新日時"),
]
SORT_KEYS = {key for key, _label in SORT_LABELS}


@dataclass(frozen=True)
class SortOrder:
    """How a folder's files, and the sibling folders around it, are lined up."""

    key: str = SORT_NAME
    descending: bool = False

    @classmethod
    def parse(cls, key: str, descending: bool) -> SortOrder:
        """Build an order from stored values, falling back on anything unknown."""
        return cls(key if key in SORT_KEYS else SORT_NAME, bool(descending))


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


if sys.platform == "win32":
    from ctypes import windll, wintypes

    # Bound once with its signature declared: ctypes otherwise re-inspects the
    # arguments on every call, and the sort makes one call per comparison.
    _str_cmp_logical = windll.shlwapi.StrCmpLogicalW
    _str_cmp_logical.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    _str_cmp_logical.restype = wintypes.INT


def windows_name_compare(left: Path, right: Path) -> int:
    return _str_cmp_logical(left.name, right.name)


def name_sorted(paths: Iterable[Path]) -> list[Path]:
    items = list(paths)
    if sys.platform == "win32":
        return sorted(items, key=cmp_to_key(windows_name_compare))
    return sorted(items, key=natural_key)


def created_time(info: os.stat_result) -> float:
    """When the file came into being.

    Windows exposes this as st_birthtime from 3.12 on and as st_ctime before.
    """
    return getattr(info, "st_birthtime", info.st_ctime)


def entry_timestamp(entry: os.DirEntry, key: str) -> float:
    """The creation or modification time behind a directory entry.

    DirEntry.stat() answers from the data the directory read already returned on
    Windows, so ordering by date costs no extra call per file; os.stat() on the
    path would, and on a folder of a few thousand it shows.
    """
    try:
        info = entry.stat()
    except OSError:
        # A file that vanished or cannot be reached sorts as the oldest rather
        # than dropping out of the listing.
        return 0.0
    return info.st_mtime if key == SORT_MODIFIED else created_time(info)


def file_times(path: Path) -> tuple[float, float] | None:
    """(created, modified) for one file, or None when it cannot be read."""
    try:
        info = path.stat()
    except OSError:
        return None
    return (created_time(info), info.st_mtime)


def sort_entries(entries: list[os.DirEntry], order: SortOrder) -> list[Path]:
    """Put directory entries in the requested order and hand back their paths."""
    if sys.platform == "win32":
        entries.sort(key=cmp_to_key(windows_name_compare))
    else:
        entries.sort(key=natural_key)
    if order.key != SORT_NAME:
        # Sorted by name first, so entries sharing a timestamp - which is common
        # for files copied together - still come out in a meaningful order.
        # Python's sort is stable, so that ordering survives underneath.
        entries.sort(key=lambda entry: entry_timestamp(entry, order.key))
    if order.descending:
        entries.reverse()
    return [Path(entry.path) for entry in entries]


def scan_media(folder: Path) -> Iterator[os.DirEntry]:
    """Yield the supported files in a folder.

    os.scandir is used rather than Path.iterdir because it carries the entry
    type back from the directory read, so telling files from folders costs no
    extra call per entry.
    """
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                name = entry.name
                # dot > 0 so a dotfile like ".jpg" is not read as an extension,
                # matching what Path.suffix reports.
                dot = name.rfind(".")
                if dot <= 0 or name[dot:].lower() not in MEDIA_EXTENSIONS:
                    continue
                try:
                    if entry.is_file():
                        yield entry
                except OSError:
                    continue
    except (OSError, ValueError):
        return


def listed_path(files: list[Path], path: Path) -> Path | None:
    """The listing's own spelling of a file in it, or None when it is not there.

    macOS may spell a Japanese name decomposed (カ followed by a separate ゛)
    in one place and composed (ガ) in another: the file dialog and the folder
    listing do not always agree. The two compare unequal as strings, so the
    names are compared in one normal form, and the listing's spelling is
    handed back for everything that follows to match against.
    """
    if path in files:
        return path
    wanted = unicodedata.normalize("NFC", path.name)
    for listed in files:
        if unicodedata.normalize("NFC", listed.name) == wanted:
            return listed
    return None


def media_files(folder: Path, order: SortOrder | None = None) -> list[Path]:
    if not folder.is_dir():
        return []
    return sort_entries(list(scan_media(folder)), order or SortOrder())


def has_media(folder: Path) -> bool:
    """Whether a folder holds anything worth opening, without listing it all."""
    return next(scan_media(folder), None) is not None


def child_folders(parent: Path, order: SortOrder | None = None) -> list[Path]:
    try:
        with os.scandir(parent) as entries:
            found = [entry for entry in entries if entry.is_dir()]
    except (OSError, ValueError):
        return []
    return sort_entries(found, order or SortOrder())


def sibling_folder(current: Path, direction: int, order: SortOrder | None = None) -> Path | None:
    siblings = child_folders(current.parent, order)
    try:
        index = siblings.index(current)
    except ValueError:
        return None
    target = index + direction
    return siblings[target] if 0 <= target < len(siblings) else None


def sibling_media_folder(
    current: Path, direction: int, order: SortOrder | None = None
) -> Path | None:
    """Find the next sibling folder that actually contains supported media."""
    siblings = child_folders(current.parent, order)
    try:
        index = siblings.index(current)
    except ValueError:
        return None
    # Walked over the one listing rather than re-reading the parent per step,
    # and each candidate is only probed for its first match.
    index += direction
    while 0 <= index < len(siblings):
        if has_media(siblings[index]):
            return siblings[index]
        index += direction
    return None
