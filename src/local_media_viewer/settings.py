from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any


@dataclass
class Favorite:
    """A bookmarked folder with the thumbnail captured when it was registered."""

    # Stable across reorders and renames; the Mac widget refers to a favorite
    # by this rather than its position in the list. Older files may lack one
    # (backfilled by favorites_from_data).
    id: str = ""
    folder: str = ""
    name: str = ""
    path: str = ""
    thumbnail: str = ""
    group: str = ""


@dataclass
class ViewerSettings:
    last_path: str = ""
    brightness: int = 0
    contrast: int = 0
    gamma: float = 1.0
    hue: int = 0
    filter_panel_visible: bool = False
    filmstrip_visible: bool = True
    toolbar_visible: bool = True
    status_bar_visible: bool = True
    volume: int = 50
    window_geometry: str = ""
    reset_pan_on_change: bool = True
    # "top", "keep" or "fixed". Empty in files written before it existed,
    # where reset_pan_on_change alone chose between top and keep.
    pan_mode: str = ""
    # The fixed pan position, as proportions of the scroll range (0 to 1).
    pan_x: float = 0.5
    pan_y: float = 0.0
    effect: str = "none"
    line_color: str = "#24478F"
    spread_view: bool = False
    spread_rtl: bool = True
    spread_cover: bool = True
    spread_anchor: int = 0
    sort_key: str = "name"
    sort_descending: bool = False
    # "" follows the Windows display language; otherwise an i18n language code.
    language: str = ""
    always_on_top: bool = False
    # "window", "width" or "height": what Space and a click fit the picture to.
    fit_kind: str = "window"
    favorites: list[Favorite] = field(default_factory=list)


def settings_path() -> Path:
    if sys.platform == "darwin":
        # Where macOS apps keep their own data; ~/AppData means nothing there.
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "LocalMediaViewer" / "settings.json"


def favorites_from_data(values: Any) -> tuple[list[Favorite], bool]:
    """Returns the favorites, and whether any of them got a backfilled id."""
    if not isinstance(values, list):
        return [], False
    allowed = Favorite.__dataclass_fields__.keys()
    favorites: list[Favorite] = []
    backfilled = False
    for item in values:
        if not isinstance(item, dict):
            continue
        favorite = Favorite(
            **{key: item[key] for key in allowed if isinstance(item.get(key), str)}
        )
        if favorite.folder:
            if not favorite.id:
                # A favorite saved before ids existed, or written by an older
                # copy of the app. Generated once and persisted by
                # load_settings so it stays the same on every later run.
                favorite = replace(favorite, id=uuid.uuid4().hex)
                backfilled = True
            favorites.append(favorite)
    return favorites, backfilled


def load_settings(path: Path | None = None) -> ViewerSettings:
    target = path or settings_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        allowed = ViewerSettings.__dataclass_fields__.keys()
        values = {key: data[key] for key in allowed if key in data}
        favorites, backfilled = favorites_from_data(values.get("favorites"))
        values["favorites"] = favorites
        settings = ViewerSettings(**values)
        if backfilled:
            # Write the generated ids back now so they are stable from here on,
            # rather than re-rolling new ones every time the file is loaded.
            save_settings(settings, target)
        return settings
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return ViewerSettings()


def save_settings(settings: ViewerSettings, path: Path | None = None) -> Path:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target
