from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Favorite:
    """A bookmarked folder with the thumbnail captured when it was registered."""

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
    volume: int = 50
    window_geometry: str = ""
    reset_pan_on_change: bool = False
    spread_view: bool = False
    spread_rtl: bool = True
    spread_anchor: int = 0
    favorites: list[Favorite] = field(default_factory=list)


def settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "LocalMediaViewer" / "settings.json"


def favorites_from_data(values: Any) -> list[Favorite]:
    if not isinstance(values, list):
        return []
    allowed = Favorite.__dataclass_fields__.keys()
    favorites: list[Favorite] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        favorite = Favorite(
            **{key: item[key] for key in allowed if isinstance(item.get(key), str)}
        )
        if favorite.folder:
            favorites.append(favorite)
    return favorites


def load_settings(path: Path | None = None) -> ViewerSettings:
    target = path or settings_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        allowed = ViewerSettings.__dataclass_fields__.keys()
        values = {key: data[key] for key in allowed if key in data}
        values["favorites"] = favorites_from_data(values.get("favorites"))
        return ViewerSettings(**values)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return ViewerSettings()


def save_settings(settings: ViewerSettings, path: Path | None = None) -> Path:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target
