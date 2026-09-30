"""Clean up block noise and raise the resolution of one picture, on demand.

Only ever run for the page the user asks for, never as a standing filter: it
takes about a second on a phone photo, far too slow to repeat on every page.

The work is behind a single function, enhance(), so a heavier backend (an AI
upscaler such as Real-ESRGAN on ONNX Runtime) can replace it later without the
window changing. This one uses Pillow alone, keeping the EXE the same size.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageFilter
from PySide6.QtCore import QObject, Signal

from local_media_viewer.preloader import load_image

# Twice the pixels on each side, unless that would pass LONGEST_SIDE.
UPSCALE = 2
# 6000 x 4500 RGBA is about 110 MB; larger pictures are cleaned but not enlarged.
LONGEST_SIDE = 6000
# Neighbour differences at or below EDGE_FLOOR are block steps to smooth over;
# at or above CORE_FLOOR they are outlines kept exactly as they are. A JPEG
# block boundary is a step of a few levels, a drawn line tens.
EDGE_FLOOR = 10
CORE_FLOOR = 40
EDGE_GAIN = 12
# Blur radii in source pixels: strong for flat areas, where the blocks show,
# light for the band around outlines, where the ringing (mosquito noise) sits.
FLAT_BLUR = 2
NEAR_BLUR = 0.7
# How far the band around outlines reaches; at least the flat blur's reach,
# or the blur bleeds outline colours into flat areas as halos.
NEAR_REACH = 2


def upscale_factor(size: tuple[int, int]) -> float:
    longest = max(size)
    if longest <= 0:
        return 1.0
    return max(1.0, min(UPSCALE, LONGEST_SIDE / longest))


def edge_mask(image: Image.Image, floor: int, reach: float, soften: float) -> Image.Image:
    """White where neighbouring pixels differ by more than `floor`.

    Widened by `reach` and softened, so the layers meet in a soft band rather
    than a visible seam. Widened by blurring and re-thresholding rather than
    MaxFilter: Pillow's rank filters took seconds on a photo.
    """
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    edges = edges.point(
        [0 if value <= floor else min(255, (value - floor) * EDGE_GAIN) for value in range(256)]
    )
    if reach:
        edges = edges.filter(ImageFilter.GaussianBlur(reach))
        edges = edges.point([0 if value < 8 else min(255, value * 8) for value in range(256)])
    return edges.filter(ImageFilter.GaussianBlur(soften))


def enhance(image: Image.Image) -> Image.Image:
    """A larger copy with the block noise smoothed away and edges kept crisp.

    Edge-aware smoothing without numpy, in three layers: flat areas are
    blurred, the band around outlines lightly so, and the outlines themselves
    stay as they were, so thin strokes are not thinned. A median filter
    cleared the ringing a little better but broke one-pixel lines into dashes
    (and was ten times slower), which matters for line art such as comics.

    Cleaned at the source size and enlarged afterwards: the same filters on
    the enlarged picture cost four times as much. A light unsharp mask
    restores the crispness the enlargement softens.
    """
    has_alpha = "A" in image.getbands()
    alpha = image.getchannel("A") if has_alpha else None
    rgb = image.convert("RGB")
    flat = rgb.filter(ImageFilter.GaussianBlur(FLAT_BLUR))
    near = rgb.filter(ImageFilter.GaussianBlur(NEAR_BLUR))
    result = Image.composite(near, flat, edge_mask(rgb, EDGE_FLOOR, NEAR_REACH, 1))
    result = Image.composite(rgb, result, edge_mask(rgb, CORE_FLOOR, 0, 0.5))
    scale = upscale_factor(rgb.size)
    if scale > 1.0:
        size = (round(rgb.width * scale), round(rgb.height * scale))
        result = result.resize(size, Image.Resampling.LANCZOS)
        if alpha is not None:
            alpha = alpha.resize(size, Image.Resampling.LANCZOS)
    # Mild on purpose: a stronger sharpen brings the ringing straight back.
    result = result.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    if alpha is not None:
        result.putalpha(alpha)
    return result


class Enhancer(QObject):
    """Runs enhance() off the UI thread, one picture at a time.

    `ready` carries the request's generation and the result, or None when the
    file could not be read. A request is dropped once cancel() or a newer
    request bumps the generation, so a slow result never lands on another page.
    """

    ready = Signal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="enhance")
        self.generation = 0
        self.closed = False

    def request(self, path: Path) -> int:
        self.generation += 1
        if not self.closed:
            self._executor.submit(self._work, self.generation, path)
        return self.generation

    def cancel(self) -> None:
        self.generation += 1

    def _work(self, generation: int, path: Path) -> None:
        if generation != self.generation:
            return
        try:
            with load_image(path) as image:
                result = enhance(image)
        except (OSError, ValueError):
            result = None
        if generation == self.generation and not self.closed:
            # Queued across threads by Qt, so the result lands on the UI thread.
            self.ready.emit(generation, result)

    def close(self) -> None:
        # Waits for a picture already in hand, as ThumbnailLoader.close() does:
        # destroying a QObject while a worker is still inside it crashes.
        self.closed = True
        self.generation += 1
        self._executor.shutdown(wait=True, cancel_futures=True)
