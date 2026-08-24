from PIL import Image

from local_media_viewer.filters import FilterValues, apply_filters


def test_filters_do_not_modify_source() -> None:
    source = Image.new("RGBA", (4, 3), (100, 120, 140, 80))
    before = source.tobytes()
    result = apply_filters(source, FilterValues(brightness=20, contrast=10, gamma=1.2, hue=45))
    assert result.size == source.size
    assert result.getchannel("A").getextrema() == (80, 80)
    assert source.tobytes() == before
