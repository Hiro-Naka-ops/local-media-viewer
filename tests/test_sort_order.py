import os
from pathlib import Path
from time import sleep

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

import local_media_viewer.app as app_module
from local_media_viewer.media import (
    SORT_CREATED,
    SORT_MODIFIED,
    SORT_NAME,
    SortOrder,
    media_files,
    sibling_media_folder,
)
from local_media_viewer.settings import ViewerSettings


def save_page(path: Path) -> None:
    Image.new("RGB", (16, 12), "teal").save(path)


def names(paths: list[Path]) -> list[str]:
    return [path.name for path in paths]


def make_window(monkeypatch, saved: list | None = None, **settings):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", lambda: ViewerSettings(**settings))
    monkeypatch.setattr(
        app_module, "save_settings", saved.append if saved is not None else lambda _s: None
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    return app_module.MainWindow()


def test_the_default_order_is_name_ascending() -> None:
    assert ViewerSettings().sort_key == SORT_NAME
    assert ViewerSettings().sort_descending is False
    assert SortOrder() == SortOrder(SORT_NAME, False)


def test_an_unknown_stored_key_falls_back_to_name() -> None:
    assert SortOrder.parse("nonsense", False).key == SORT_NAME
    assert SortOrder.parse("", True) == SortOrder(SORT_NAME, True)
    assert SortOrder.parse(SORT_MODIFIED, True) == SortOrder(SORT_MODIFIED, True)


def test_name_order_runs_both_ways(tmp_path: Path) -> None:
    for name in ("charlie.png", "alpha.png", "bravo.png"):
        save_page(tmp_path / name)
    ascending = ["alpha.png", "bravo.png", "charlie.png"]
    assert names(media_files(tmp_path, SortOrder(SORT_NAME, False))) == ascending
    assert names(media_files(tmp_path, SortOrder(SORT_NAME, True))) == ascending[::-1]


def test_modified_order_runs_both_ways(tmp_path: Path) -> None:
    for name in ("alpha.png", "bravo.png", "charlie.png"):
        save_page(tmp_path / name)
    # Set the times outright rather than sleeping, so the order is exact.
    for name, when in (("alpha.png", 3000), ("bravo.png", 1000), ("charlie.png", 2000)):
        os.utime(tmp_path / name, (when, when))
    oldest_first = ["bravo.png", "charlie.png", "alpha.png"]
    assert names(media_files(tmp_path, SortOrder(SORT_MODIFIED, False))) == oldest_first
    assert names(media_files(tmp_path, SortOrder(SORT_MODIFIED, True))) == oldest_first[::-1]


def test_created_order_follows_the_order_files_appeared(tmp_path: Path) -> None:
    written = ["charlie.png", "alpha.png", "bravo.png"]
    for name in written:
        save_page(tmp_path / name)
        # The Windows clock only ticks every ~15ms, so without this the three
        # could share a creation time and fall back to the name order.
        sleep(0.05)
    assert names(media_files(tmp_path, SortOrder(SORT_CREATED, False))) == written
    assert names(media_files(tmp_path, SortOrder(SORT_CREATED, True))) == written[::-1]


def test_files_sharing_a_timestamp_keep_the_name_order(tmp_path: Path) -> None:
    for name in ("charlie.png", "alpha.png", "bravo.png"):
        save_page(tmp_path / name)
        os.utime(tmp_path / name, (5000, 5000))
    # Copied-together files routinely share a stamp; they must not come out in
    # whatever order the directory happened to hand them over.
    assert names(media_files(tmp_path, SortOrder(SORT_MODIFIED, False))) == [
        "alpha.png",
        "bravo.png",
        "charlie.png",
    ]


def test_numeric_names_still_sort_logically_under_a_date_key(tmp_path: Path) -> None:
    for name in ("10.png", "2.png", "1.png"):
        save_page(tmp_path / name)
        os.utime(tmp_path / name, (7000, 7000))
    assert names(media_files(tmp_path, SortOrder(SORT_MODIFIED, False))) == [
        "1.png",
        "2.png",
        "10.png",
    ]


def test_sibling_folders_follow_the_same_order(tmp_path: Path) -> None:
    for name in ("c_book", "a_book", "b_book"):
        folder = tmp_path / name
        folder.mkdir()
        save_page(folder / "p.png")
    here = tmp_path / "b_book"

    ascending = SortOrder(SORT_NAME, False)
    assert sibling_media_folder(here, -1, ascending) == tmp_path / "a_book"
    assert sibling_media_folder(here, 1, ascending) == tmp_path / "c_book"

    # Descending turns the neighbours around, so 前へ and 次へ keep matching
    # what the list on screen shows.
    descending = SortOrder(SORT_NAME, True)
    assert sibling_media_folder(here, -1, descending) == tmp_path / "c_book"
    assert sibling_media_folder(here, 1, descending) == tmp_path / "a_book"


def test_changing_the_order_stays_on_the_same_picture(tmp_path: Path, monkeypatch) -> None:
    for name, when in (("alpha.png", 3000), ("bravo.png", 1000), ("charlie.png", 2000)):
        save_page(tmp_path / name)
        os.utime(tmp_path / name, (when, when))

    window = make_window(monkeypatch)
    try:
        window.open_folder(tmp_path, 0)
        window.navigate(1)
        assert window.files[window.index].name == "bravo.png"

        window.choose_sort_key(SORT_MODIFIED)
        assert names(window.files) == ["bravo.png", "charlie.png", "alpha.png"]
        # Reordering moves the picture to a different index; the reader's place
        # follows the file rather than the slot it used to sit in.
        assert window.files[window.index].name == "bravo.png"
        assert window.index == 0

        window.sort_descending_action.setChecked(True)
        assert names(window.files) == ["alpha.png", "charlie.png", "bravo.png"]
        assert window.files[window.index].name == "bravo.png"
        assert window.index == 2
    finally:
        window.close()


def test_the_order_reaches_the_filmstrip(tmp_path: Path, monkeypatch) -> None:
    for name in ("charlie.png", "alpha.png", "bravo.png"):
        save_page(tmp_path / name)

    window = make_window(monkeypatch)
    try:
        window.open_folder(tmp_path, 0)
        assert names(window.filmstrip.files) == ["alpha.png", "bravo.png", "charlie.png"]
        window.sort_descending_action.setChecked(True)
        assert names(window.filmstrip.files) == ["charlie.png", "bravo.png", "alpha.png"]
    finally:
        window.close()


def test_reordering_starts_the_spread_pairing_over(tmp_path: Path, monkeypatch) -> None:
    for index in range(6):
        save_page(tmp_path / f"{index}.png")

    window = make_window(monkeypatch)
    try:
        window.open_folder(tmp_path, 0)
        window.spread_action.setChecked(True)
        window.navigate(1)
        window.shift_spread()
        assert window.displayed_pages == [2, 3]

        # A new running order is a new book, so the cover rule applies again
        # rather than keeping an offset measured against the old order.
        window.sort_descending_action.setChecked(True)
        assert window.spread_anchor == window.default_spread_anchor()
    finally:
        window.close()


def test_the_order_survives_a_settings_round_trip(tmp_path: Path, monkeypatch) -> None:
    save_page(tmp_path / "a.png")
    stored: list[ViewerSettings] = []
    window = make_window(monkeypatch, stored)
    try:
        window.open_folder(tmp_path, 0)
        window.choose_sort_key(SORT_CREATED)
        window.sort_descending_action.setChecked(True)
    finally:
        window.close()

    saved = stored[-1]
    assert saved.sort_key == SORT_CREATED
    assert saved.sort_descending is True

    monkeypatch.setattr(app_module, "load_settings", lambda: saved)
    restored = app_module.MainWindow()
    try:
        assert restored.sort_order == SortOrder(SORT_CREATED, True)
        assert restored.sort_actions[SORT_CREATED].isChecked() is True
        assert restored.sort_descending_action.isChecked() is True
    finally:
        restored.close()


def test_only_one_field_is_checked_at_a_time(tmp_path: Path, monkeypatch) -> None:
    save_page(tmp_path / "a.png")
    window = make_window(monkeypatch)
    try:
        window.open_folder(tmp_path, 0)
        for key in (SORT_CREATED, SORT_MODIFIED, SORT_NAME):
            window.choose_sort_key(key)
            checked = [name for name, a in window.sort_actions.items() if a.isChecked()]
            assert checked == [key]
    finally:
        window.close()
