from pathlib import Path

from local_media_viewer.settings import ViewerSettings, load_settings, save_settings


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    expected = ViewerSettings(
        last_path="C:/画像/sample.webp",
        brightness=15,
        contrast=-8,
        gamma=1.3,
        hue=45,
        filter_panel_visible=True,
        filmstrip_visible=False,
        volume=75,
        window_geometry="geometry",
    )
    assert save_settings(expected, path) == path
    assert load_settings(path) == expected


def test_broken_settings_use_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("broken", encoding="utf-8")
    assert load_settings(path) == ViewerSettings()
