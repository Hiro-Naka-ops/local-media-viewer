from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


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


def settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "LocalMediaViewer" / "settings.json"


def load_settings(path: Path | None = None) -> ViewerSettings:
    target = path or settings_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        allowed = ViewerSettings.__dataclass_fields__.keys()
        return ViewerSettings(**{key: data[key] for key in allowed if key in data})
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return ViewerSettings()


def save_settings(settings: ViewerSettings, path: Path | None = None) -> Path:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target
