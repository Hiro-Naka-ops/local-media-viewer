from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from PIL import Image
from PySide6.QtGui import QImage

from local_media_viewer import heic  # noqa: F401  (registers the HEIC decoder)


@dataclass
class Frame:
    """A decoded page, held either as a QImage or as a Pillow image.

    A still that needs no filtering is decoded straight to QImage, which skips
    copying the whole bitmap out of Pillow and back into Qt. Anything Pillow has
    to work on - filters, effects, a spread, an animation - keeps its handle.
    """

    qimage: QImage | None = None
    image: Image.Image | None = None

    def close(self) -> None:
        if self.image is not None:
            self.image.close()
            self.image = None
        self.qimage = None


def load_image(path: Path) -> Image.Image:
    image = Image.open(path)
    image.seek(0)
    image.load()
    return image


def load_qimage(path: Path) -> QImage:
    """Decode with Qt. Safe off the UI thread; QPixmap would not be."""
    image = QImage()
    image.load(str(path))
    return image


def is_animated_file(path: Path) -> bool:
    """Read just the header to see whether the file has more than one frame.

    Qt is not asked because its PNG handler reports an APNG as a single frame,
    which would quietly turn an animation into a still.
    """
    try:
        with Image.open(path) as probe:
            return int(getattr(probe, "n_frames", 1)) > 1
    except (OSError, ValueError):
        return False


def load_frame(path: Path, plain: bool) -> Frame:
    """Decode one page by whichever route the current view can use."""
    if plain and not is_animated_file(path):
        qimage = load_qimage(path)
        if not qimage.isNull():
            return Frame(qimage=qimage)
    return Frame(image=load_image(path))


def close_future_frame(future: Future[Frame]) -> None:
    if not future.cancelled() and future.exception() is None:
        future.result().close()


class ImagePreloader:
    """Keeps a small, bounded set of nearby pages decoded in the background."""

    def __init__(self, workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="image-preload")
        self._futures: dict[Path, Future[Frame]] = {}
        self._lock = Lock()
        self._plain = True

    def preload(self, paths: list[Path], plain: bool = True) -> None:
        wanted = set(paths)
        with self._lock:
            if plain != self._plain:
                # The decode route changed, so what is already queued is the
                # wrong kind of Frame and is thrown away rather than handed out.
                self._plain = plain
                wanted = set()
            for path in list(self._futures):
                if path not in wanted:
                    self._discard_locked(path)
            for path in paths:
                if path not in self._futures:
                    self._futures[path] = self._executor.submit(load_frame, path, plain)

    def take(self, path: Path, plain: bool = True) -> Frame | None:
        with self._lock:
            if plain != self._plain:
                # The view started needing the other kind of Frame since these
                # were queued - turning a spread on, say - so handing one over
                # would quietly show the page by the wrong route.
                for queued in list(self._futures):
                    self._discard_locked(queued)
                self._plain = plain
                return None
            future = self._futures.pop(path, None)
        if future is None:
            return None
        if future.done() and not future.cancelled() and future.exception() is None:
            return future.result()
        if not future.cancel():
            future.add_done_callback(close_future_frame)
        return None

    def close(self) -> None:
        with self._lock:
            for path in list(self._futures):
                self._discard_locked(path)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _discard_locked(self, path: Path) -> None:
        future = self._futures.pop(path)
        if future.done():
            close_future_frame(future)
        elif not future.cancel():
            future.add_done_callback(close_future_frame)
