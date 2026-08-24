import pytest

from local_media_viewer.controls import snap_value


def test_snap_value_uses_twenty_divisions() -> None:
    assert snap_value(36, -100, 100, 0) == 40
    assert snap_value(-74, -100, 100, 0) == -70


def test_default_is_always_an_independent_snap_point() -> None:
    # Gamma's regular marks include 90 and 104; its exact default is still selectable.
    assert snap_value(99, 20, 300, 100) == 100
    assert snap_value(101, 20, 300, 100) == 100


def test_gamma_scale_uses_twenty_point_steps_including_default() -> None:
    assert snap_value(91, 20, 300, 100, divisions=14) == 100
    assert snap_value(111, 20, 300, 100, divisions=14) == 120


def test_range_ends_are_scale_marks() -> None:
    assert snap_value(-99, -100, 100, 0) == -100
    assert snap_value(299, 20, 300, 100) == 300


def test_invalid_division_count_is_rejected() -> None:
    with pytest.raises(ValueError):
        snap_value(0, -100, 100, 0, divisions=0)
