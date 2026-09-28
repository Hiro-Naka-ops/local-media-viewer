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


def test_every_filter_moves_three_per_mark_and_keeps_its_default() -> None:
    from PySide6.QtWidgets import QApplication

    from local_media_viewer.app import (
        BRIGHTNESS_RANGE,
        CONTRAST_RANGE,
        GAMMA_RANGE,
        HUE_RANGE,
    )
    from local_media_viewer.controls import SnappingSlider

    QApplication.instance() or QApplication([])
    for (minimum, maximum), default in [
        (BRIGHTNESS_RANGE, 0),
        (CONTRAST_RANGE, 0),
        (GAMMA_RANGE, 100),
        (HUE_RANGE, 0),
    ]:
        slider = SnappingSlider(minimum, maximum, default, default)
        marks = slider.marks()
        assert {b - a for a, b in zip(marks, marks[1:])} == {3}
        # The reset value is one of the regular marks, not an odd one out.
        assert default in marks


def test_marks_are_evenly_spaced_under_any_style() -> None:
    from PySide6.QtWidgets import QApplication, QStyleFactory, QStyleOptionSlider

    from local_media_viewer.controls import SnappingSlider

    app = QApplication.instance() or QApplication([])
    for name in QStyleFactory.keys():
        slider = SnappingSlider(-30, 30, 0, 0)
        slider.setStyle(QStyleFactory.create(name))
        slider.resize(237, 40)  # an awkward width that does not divide evenly
        slider.show()
        app.processEvents()
        option = QStyleOptionSlider()
        slider.initStyleOption(option)
        xs = [slider.value_x(option, mark) for mark in slider.marks()]
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        assert max(gaps) - min(gaps) < 1e-6, name
        # The ends sit where the style centres the handle at each end.
        assert xs[0] == slider.handle_centre(option, -30)
        assert xs[-1] == slider.handle_centre(option, 30)
        slider.close()


def test_values_saved_under_the_old_wide_ranges_are_brought_inside(monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication

    import local_media_viewer.app as app_module
    from local_media_viewer.settings import ViewerSettings

    QApplication.instance() or QApplication([])
    old = ViewerSettings(brightness=60, contrast=-80, gamma=2.4, hue=120)
    monkeypatch.setattr(app_module, "load_settings", lambda: old)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    window = app_module.MainWindow()
    try:
        # Clamped to the nearest end rather than lost or wrapped round.
        values = window.filter_values()
        assert (values.brightness, values.contrast, values.gamma, values.hue) == (
            30,
            -30,
            1.3,
            30,
        )
    finally:
        window.close()
