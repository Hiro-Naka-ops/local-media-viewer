import json
import sys
import threading
import time

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from local_media_viewer import mac_widget
from local_media_viewer.favorites import encode_thumbnail
from local_media_viewer.settings import Favorite, favorites_from_data, load_settings


def solid_thumbnail() -> str:
    QApplication.instance() or QApplication([])
    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor("#336699"))
    return encode_thumbnail(pixmap)


def test_favorites_from_data_backfills_a_missing_id() -> None:
    favorites, backfilled = favorites_from_data([{"folder": "/pictures/trip"}])
    assert backfilled is True
    assert len(favorites) == 1
    assert favorites[0].id  # something was generated
    assert favorites[0].folder == "/pictures/trip"


def test_favorites_from_data_leaves_an_existing_id_alone() -> None:
    favorites, backfilled = favorites_from_data(
        [{"folder": "/pictures/trip", "id": "kept-id"}]
    )
    assert backfilled is False
    assert favorites[0].id == "kept-id"


def test_favorites_from_data_drops_entries_without_a_folder() -> None:
    favorites, _backfilled = favorites_from_data([{"name": "no folder here"}])
    assert favorites == []


def test_load_settings_persists_a_backfilled_id_so_it_stays_stable(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"favorites": [{"folder": "/pictures/trip"}]}), encoding="utf-8")

    first = load_settings(path)
    second = load_settings(path)

    assert first.favorites[0].id
    assert first.favorites[0].id == second.favorites[0].id


def test_widget_container_is_none_off_macos(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert mac_widget.widget_container() is None


def test_widget_container_lives_under_group_containers_on_macos(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mac_widget.Path, "home", classmethod(lambda cls: tmp_path))
    container = mac_widget.widget_container()
    assert container is not None
    assert container.parts[-3:-1] == ("Library", "Group Containers")
    assert container.name == mac_widget.APP_GROUP_ID


def test_parse_widget_favorite_id_reads_the_id_query_param() -> None:
    url = f"{mac_widget.URL_SCHEME}://favorite?id=abc123"
    assert mac_widget.parse_widget_favorite_id(url) == "abc123"


def test_parse_widget_favorite_id_rejects_other_schemes() -> None:
    assert mac_widget.parse_widget_favorite_id("https://example.com?id=abc123") is None


def test_parse_widget_favorite_id_is_none_without_an_id() -> None:
    assert mac_widget.parse_widget_favorite_id(f"{mac_widget.URL_SCHEME}://favorite") is None


def test_resolve_favorite_finds_the_matching_entry() -> None:
    favorites = [
        Favorite(id="a", folder="/one"),
        Favorite(id="b", folder="/two"),
    ]
    assert mac_widget.resolve_favorite(favorites, "b") is favorites[1]
    assert mac_widget.resolve_favorite(favorites, "missing") is None


def test_export_writes_nothing_off_macos(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    mac_widget.export_favorites_for_widget([Favorite(id="a", folder="/one")])
    assert not (tmp_path / mac_widget.APP_GROUP_ID).exists()


def test_export_writes_favorites_json_and_a_thumbnail_per_entry(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mac_widget.Path, "home", classmethod(lambda cls: tmp_path))

    favorite = Favorite(
        id="fav-1",
        folder="/pictures/trip",
        name="Trip",
        group="Travel",
        thumbnail=solid_thumbnail(),
    )
    mac_widget.export_favorites_for_widget([favorite])

    container = mac_widget.widget_container()
    payload = json.loads((container / mac_widget.FAVORITES_FILENAME).read_text(encoding="utf-8"))
    assert payload == [{"id": "fav-1", "name": "Trip", "group": "Travel", "order": 0}]
    assert (container / mac_widget.THUMBNAILS_DIRNAME / "fav-1.png").is_file()


def test_export_writes_a_square_thumbnail_for_a_non_square_favorite(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mac_widget.Path, "home", classmethod(lambda cls: tmp_path))

    QApplication.instance() or QApplication([])
    wide = QPixmap(200, 100)
    wide.fill(QColor("#336699"))
    favorite = Favorite(id="wide", folder="/a", name="A", thumbnail=encode_thumbnail(wide))
    monkeypatch.setattr(mac_widget, "_source_pixmap", lambda fav: wide)

    mac_widget.export_favorites_for_widget([favorite])

    container = mac_widget.widget_container()
    saved = QPixmap(str(container / mac_widget.THUMBNAILS_DIRNAME / "wide.png"))
    assert saved.width() == saved.height()


def test_export_prunes_thumbnails_for_favorites_no_longer_registered(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mac_widget.Path, "home", classmethod(lambda cls: tmp_path))

    thumbnail = solid_thumbnail()
    kept = Favorite(id="keep", folder="/a", name="A", thumbnail=thumbnail)
    removed = Favorite(id="drop", folder="/b", name="B", thumbnail=thumbnail)
    mac_widget.export_favorites_for_widget([kept, removed])

    container = mac_widget.widget_container()
    thumbnails = container / mac_widget.THUMBNAILS_DIRNAME
    assert (thumbnails / "keep.png").is_file()
    assert (thumbnails / "drop.png").is_file()

    mac_widget.export_favorites_for_widget([kept])

    assert (thumbnails / "keep.png").is_file()
    assert not (thumbnails / "drop.png").is_file()


def test_export_falls_back_to_the_stored_thumbnail_when_the_original_file_is_gone(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mac_widget.Path, "home", classmethod(lambda cls: tmp_path))

    favorite = Favorite(
        id="fav-2",
        folder="/pictures/trip",
        name="Trip",
        path="/pictures/trip/does-not-exist.jpg",
        thumbnail=solid_thumbnail(),
    )
    mac_widget.export_favorites_for_widget([favorite])

    container = mac_widget.widget_container()
    thumbnail_path = container / mac_widget.THUMBNAILS_DIRNAME / "fav-2.png"
    assert thumbnail_path.is_file()
    saved = QPixmap(str(thumbnail_path))
    assert not saved.isNull()


def test_export_gives_up_on_a_source_file_that_never_responds(monkeypatch, tmp_path) -> None:
    """A stale network/external-drive mount must not hang the export.

    load_image() blocking forever (as a stat() on a dead SMB share can) must
    not stop export_favorites_for_widget() from finishing quickly and still
    writing the stored thumbnail instead.
    """
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mac_widget.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(mac_widget, "NETWORK_READ_TIMEOUT", 0.05)

    released = threading.Event()

    def hangs_forever(_path):
        released.wait()  # never set: simulates a syscall that never returns
        raise AssertionError("should have been abandoned before returning")

    monkeypatch.setattr(mac_widget, "load_image", hangs_forever)

    favorite = Favorite(
        id="fav-3",
        folder="/pictures/trip",
        name="Trip",
        path="/Volumes/offline-nas/trip/does-not-respond.jpg",
        thumbnail=solid_thumbnail(),
    )

    started = time.monotonic()
    mac_widget.export_favorites_for_widget([favorite])
    elapsed = time.monotonic() - started

    assert elapsed < 2.0  # nowhere near hanging; well under any real timeout
    container = mac_widget.widget_container()
    thumbnail_path = container / mac_widget.THUMBNAILS_DIRNAME / "fav-3.png"
    assert thumbnail_path.is_file()
