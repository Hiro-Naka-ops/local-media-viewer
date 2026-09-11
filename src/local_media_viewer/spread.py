from __future__ import annotations

from PIL import Image


def scaled_to_height(page: Image.Image, height: int) -> Image.Image:
    """Bring a page to the shared spread height so the two halves line up."""
    if page.height == height:
        return page
    width = max(1, round(page.width * height / page.height))
    resampling = (
        Image.Resampling.LANCZOS if height < page.height else Image.Resampling.BICUBIC
    )
    return page.resize((width, height), resampling)


def compose_spread(
    first: Image.Image,
    second: Image.Image,
    right_to_left: bool,
) -> Image.Image:
    """Join two pages into one image with no seam between them.

    Some works draw a single picture across both pages, so the halves are put
    edge to edge with no gap and matched in height rather than padded.
    """
    height = max(first.height, second.height)
    left, right = (second, first) if right_to_left else (first, second)
    left = scaled_to_height(left, height)
    right = scaled_to_height(right, height)
    canvas = Image.new("RGBA", (left.width + right.width, height))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width, 0))
    return canvas


def is_animated(image: Image.Image) -> bool:
    return int(getattr(image, "n_frames", 1)) > 1
