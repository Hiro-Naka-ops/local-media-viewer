from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageEnhance


@dataclass
class FilterValues:
    brightness: int = 0
    contrast: int = 0
    gamma: float = 1.0
    hue: int = 0


def apply_filters(image: Image.Image, values: FilterValues) -> Image.Image:
    has_alpha = "A" in image.getbands()
    alpha = image.getchannel("A") if has_alpha else None
    result = image.convert("RGB")
    result = ImageEnhance.Brightness(result).enhance(max(0, 1 + values.brightness / 100))
    result = ImageEnhance.Contrast(result).enhance(max(0, 1 + values.contrast / 100))
    if values.gamma != 1.0:
        inverse = 1 / max(0.1, values.gamma)
        table = [round(255 * ((value / 255) ** inverse)) for value in range(256)]
        result = result.point(table * 3)
    if values.hue:
        hsv = result.convert("HSV")
        hue, saturation, value = hsv.split()
        shift = round(values.hue / 360 * 255)
        hue = hue.point([(item + shift) % 256 for item in range(256)])
        result = Image.merge("HSV", (hue, saturation, value)).convert("RGB")
    if alpha is not None:
        result.putalpha(alpha)
    return result
