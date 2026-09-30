"""Feeds the Mac desktop widget (mac-widget/) with the favorites list.

The widget itself is a Swift/WidgetKit extension living outside this Python
package (see mac-widget/ and its own README). It runs sandboxed and cannot
read arbitrary folders on disk, so this module writes what it needs — a
favorites.json plus a PNG per favorite — into a shared App Group container
that both sides can see. The widget only ever reads; this module is the only
writer.

A no-op everywhere except macOS: export_favorites_for_widget() returns
immediately on Windows, and every other function here is only meaningful once
a widget has been built, so nothing in app.py needs to branch on platform
itself.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap

from local_media_viewer.media import IMAGE_EXTENSIONS
from local_media_viewer.preloader import load_image
from local_media_viewer.settings import Favorite

# A favorite's original file can live on a network share or an external
# drive that has since gone offline; the very first stat() on a dead mount
# can block for a long time (macOS's own SMB/AFP timeout, well past what a
# user waiting on "register favorite" or app startup should sit through).
# Reading it is bounded to this many seconds before giving up on the sharper
# original and falling back to the thumbnail already cached in settings.
NETWORK_READ_TIMEOUT = 3.0

# Must match the App Group entered under Signing & Capabilities for both the
# widget's container app and the FavoritesWidget extension target in Xcode.
APP_GROUP_ID = "group.io.github.local-media-viewer"

# Must match the CFBundleURLSchemes entry scripts/build_mac.sh adds to
# Info.plist, and the widgetURL each widget entry links to.
URL_SCHEME = "localmediaviewer"

# Side length of the square PNG written per favorite. Generous enough for the
# systemLarge layout's big tiles at Retina resolution; SwiftUI downscales it
# for the smaller tiles itself.
THUMBNAIL_LONG_SIDE = 600

FAVORITES_FILENAME = "favorites.json"
THUMBNAILS_DIRNAME = "thumbnails"


def widget_container() -> Path | None:
    """Where the widget's data is written, or None off macOS.

    This app is not sandboxed, so it can create the App Group container
    itself, before the (sandboxed) widget extension has ever run — macOS
    resolves both sides to the same directory once the extension carries a
    matching App Groups entitlement.
    """
    if sys.platform != "darwin":
        return None
    return Path.home() / "Library" / "Group Containers" / APP_GROUP_ID


def favorite_display_name(favorite: Favorite) -> str:
    return favorite.name or Path(favorite.folder).name or favorite.folder


def _read_image_with_timeout(path: Path, timeout: float) -> Image.Image | None:
    """load_image(path), abandoned rather than awaited past `timeout`.

    Runs on a throwaway daemon thread: Python cannot cancel a blocked
    syscall, so a path on an unreachable network share leaves that one
    thread stuck rather than the caller. Each call gets its own thread
    (never a shared pool) so one dead mount can never queue up and stall the
    check for a later, perfectly reachable favorite.
    """
    outcome: list[Image.Image] = []

    def read() -> None:
        try:
            outcome.append(load_image(path))
        except OSError:
            pass

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    worker.join(timeout=timeout)
    return outcome[0] if outcome else None


def _source_pixmap(favorite: Favorite) -> QPixmap:
    """The best image available for one favorite.

    Prefers re-decoding the original file (sharper, and not letterboxed like
    the 64x40 thumbnail kept in settings); a video, a moved or deleted file,
    an unresponsive network/external drive, or a decode failure all fall
    back to that stored thumbnail instead of exporting nothing.
    """
    path = Path(favorite.path) if favorite.path else None
    if path is not None and path.suffix.lower() in IMAGE_EXTENSIONS:
        image = _read_image_with_timeout(path, NETWORK_READ_TIMEOUT)
        if image is not None:
            try:
                pixmap = QPixmap.fromImage(ImageQt(image.convert("RGBA")))
            finally:
                image.close()
            if not pixmap.isNull():
                return pixmap
    from local_media_viewer.favorites import decode_thumbnail

    return decode_thumbnail(favorite.thumbnail)


def _scaled_down(pixmap: QPixmap, long_side: int) -> QPixmap:
    if pixmap.isNull():
        return pixmap
    size = pixmap.size()
    factor = long_side / max(size.width(), size.height())
    target = QSize(
        max(1, round(size.width() * factor)),
        max(1, round(size.height() * factor)),
    )
    return pixmap.scaled(
        target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


def export_favorites_for_widget(favorites: list[Favorite]) -> None:
    """Best-effort refresh of the widget's data. Never raises."""
    container = widget_container()
    if container is None:
        return
    thumbnails_dir = container / THUMBNAILS_DIRNAME
    try:
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    entries = []
    kept_ids = set()
    for order, favorite in enumerate(favorites):
        if not favorite.id:
            continue
        kept_ids.add(favorite.id)
        entries.append(
            {
                "id": favorite.id,
                "name": favorite_display_name(favorite),
                "group": favorite.group,
                "order": order,
            }
        )
        from local_media_viewer.favorites import center_square_crop

        pixmap = _scaled_down(center_square_crop(_source_pixmap(favorite)), THUMBNAIL_LONG_SIDE)
        if not pixmap.isNull():
            pixmap.save(str(thumbnails_dir / f"{favorite.id}.png"), "PNG")

    try:
        for existing in thumbnails_dir.glob("*.png"):
            if existing.stem not in kept_ids:
                existing.unlink(missing_ok=True)

        payload_path = container / FAVORITES_FILENAME
        temporary = payload_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(payload_path)
    except OSError:
        return


def parse_widget_favorite_id(url: str) -> str | None:
    """The favorite id carried by one of our own widgetURL links, if any."""
    parsed = urlparse(url)
    if parsed.scheme != URL_SCHEME:
        return None
    values = parse_qs(parsed.query).get("id")
    return values[0] if values else None


def resolve_favorite(favorites: list[Favorite], favorite_id: str) -> Favorite | None:
    for favorite in favorites:
        if favorite.id == favorite_id:
            return favorite
    return None
