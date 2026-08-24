from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from PIL import Image


def load_image(path: Path) -> Image.Image:
    image = Image.open(path)
    image.seek(0)
    image.load()
    return image


def close_future_image(future: Future[Image.Image]) -> None:
    if not future.cancelled() and future.exception() is None:
        future.result().close()


class ImagePreloader:
    """Keeps a small, bounded set of nearby images decoded in the background."""

    def __init__(self, workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="image-preload")
        self._futures: dict[Path, Future[Image.Image]] = {}
        self._lock = Lock()

    def preload(self, paths: list[Path]) -> None:
        wanted = set(paths)
        with self._lock:
            for path in list(self._futures):
                if path not in wanted:
                    self._discard_locked(path)
            for path in paths:
                if path not in self._futures:
                    self._futures[path] = self._executor.submit(load_image, path)

    def take(self, path: Path) -> Image.Image | None:
        with self._lock:
            future = self._futures.pop(path, None)
        if future is None:
            return None
        if future.done() and not future.cancelled() and future.exception() is None:
            return future.result()
        if not future.cancel():
            future.add_done_callback(close_future_image)
        return None

    def close(self) -> None:
        with self._lock:
            for path in list(self._futures):
                self._discard_locked(path)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _discard_locked(self, path: Path) -> None:
        future = self._futures.pop(path)
        if future.done():
            close_future_image(future)
        elif not future.cancel():
            future.add_done_callback(close_future_image)
