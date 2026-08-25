from local_media_viewer.viewer import format_media_time


def test_format_media_time() -> None:
    assert format_media_time(0) == "00:00"
    assert format_media_time(65_999) == "01:05"
    assert format_media_time(3_661_000) == "1:01:01"
    assert format_media_time(-100) == "00:00"
