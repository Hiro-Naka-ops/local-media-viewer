from __future__ import annotations

from PIL import Image, ImageOps

NONE = "none"
MONOCHROME = "monochrome"
SEPIA = "sepia"
LINE_COLOR = "line_color"

# Shown in the エフェクト submenu, in this order. The labels are i18n keys.
EFFECT_LABELS: list[tuple[str, str]] = [
    (NONE, "なし"),
    (MONOCHROME, "モノクロ"),
    (SEPIA, "セピア"),
    (LINE_COLOR, "線の色を変える"),
]

SEPIA_DARK = (38, 24, 10)
SEPIA_LIGHT = (255, 240, 204)
DEFAULT_LINE_COLOR = "#24478F"


def parse_color(value: str) -> tuple[int, int, int]:
    """Read a #rrggbb string, falling back to the default line colour."""
    text = value.strip().lstrip("#")
    if len(text) == 6:
        try:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        except ValueError:
            pass
    fallback = DEFAULT_LINE_COLOR.lstrip("#")
    return (
        int(fallback[0:2], 16),
        int(fallback[2:4], 16),
        int(fallback[4:6], 16),
    )


def gradient_map(
    image: Image.Image,
    dark: tuple[int, int, int],
    light: tuple[int, int, int],
) -> Image.Image:
    """Re-tint by brightness: the darkest pixels become `dark`, the lightest `light`.

    Line art keeps its shading this way, because midtones land between the two
    ends rather than being flattened to a single colour.
    """
    has_alpha = "A" in image.getbands()
    alpha = image.getchannel("A") if has_alpha else None
    result = ImageOps.colorize(image.convert("L"), black=dark, white=light)
    if alpha is not None:
        result = result.convert("RGBA")
        result.putalpha(alpha)
    return result


def apply_effect(image: Image.Image, effect: str, line_color: str) -> Image.Image:
    if effect == MONOCHROME:
        return gradient_map(image, (0, 0, 0), (255, 255, 255))
    if effect == SEPIA:
        return gradient_map(image, SEPIA_DARK, SEPIA_LIGHT)
    if effect == LINE_COLOR:
        # Black goes to the chosen colour while white stays white, so the
        # drawing is recoloured without tinting the paper.
        return gradient_map(image, parse_color(line_color), (255, 255, 255))
    return image
