from pathlib import Path

from local_media_viewer.media import (
    has_media,
    media_files,
    name_sorted,
    sibling_folder,
    sibling_media_folder,
)


def test_media_files_use_natural_order(tmp_path: Path) -> None:
    for name in ["image10.webp", "image2.png", "ignore.txt", "clip.mp4"]:
        (tmp_path / name).write_bytes(b"test")
    assert [item.name for item in media_files(tmp_path)] == ["clip.mp4", "image2.png", "image10.webp"]


def test_sibling_folder_navigation(tmp_path: Path) -> None:
    folders = [tmp_path / name for name in ["10", "2", "1"]]
    for folder in folders:
        folder.mkdir()
    assert sibling_folder(tmp_path / "2", -1).name == "1"
    assert sibling_folder(tmp_path / "2", 1).name == "10"
    assert sibling_folder(tmp_path / "1", -1) is None


def test_sibling_media_folder_skips_folders_without_media(tmp_path: Path) -> None:
    first = tmp_path / "1"
    empty = tmp_path / "2"
    last = tmp_path / "3"
    for folder in (first, empty, last):
        folder.mkdir()
    (first / "first.png").write_bytes(b"image")
    (empty / "notes.txt").write_text("not media", encoding="utf-8")
    (last / "last.webp").write_bytes(b"image")

    assert sibling_media_folder(first, 1) == last
    assert sibling_media_folder(last, -1) == first
    assert sibling_media_folder(last, 1) is None


def test_windows_name_sort_handles_numeric_names(tmp_path: Path) -> None:
    paths = [tmp_path / name for name in ["folder10", "folder02", "folder1", "folder2"]]
    assert [path.name for path in name_sorted(paths)] == [
        "folder1",
        "folder02",
        "folder2",
        "folder10",
    ]


def test_has_media_stops_at_the_first_match(tmp_path: Path) -> None:
    assert has_media(tmp_path) is False
    (tmp_path / "notes.txt").write_text("not media", encoding="utf-8")
    assert has_media(tmp_path) is False
    (tmp_path / "page.png").write_bytes(b"image")
    assert has_media(tmp_path) is True


def test_a_dotfile_is_not_read_as_an_extension(tmp_path: Path) -> None:
    (tmp_path / ".png").write_bytes(b"image")
    (tmp_path / "real.png").write_bytes(b"image")
    assert [item.name for item in media_files(tmp_path)] == ["real.png"]


def test_scanning_ignores_folders_named_like_media(tmp_path: Path) -> None:
    (tmp_path / "album.png").mkdir()
    (tmp_path / "page.png").write_bytes(b"image")
    assert [item.name for item in media_files(tmp_path)] == ["page.png"]


def test_missing_folder_scans_as_empty(tmp_path: Path) -> None:
    assert media_files(tmp_path / "gone") == []
    assert has_media(tmp_path / "gone") is False
