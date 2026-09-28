from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

import local_media_viewer.app as app_module
from local_media_viewer.media import SORT_CREATED, SORT_MODIFIED, SORT_NAME
from local_media_viewer.settings import ViewerSettings
from local_media_viewer.sorticon import sort_icon

COLOR = "#98A2B3"
COMBINATIONS = [
    (key, descending)
    for key in (SORT_NAME, SORT_CREATED, SORT_MODIFIED)
    for descending in (False, True)
]


def make_window(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    return app_module.MainWindow()


def painted_pixels(pixmap) -> int:
    image = pixmap.toImage()
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )


def test_every_combination_draws_something() -> None:
    QApplication.instance() or QApplication([])
    for key, descending in COMBINATIONS:
        pixmap = sort_icon(key, descending, 16, COLOR)
        assert not pixmap.isNull()
        # A malformed path would render an empty box without raising, so the
        # ink is what gets checked rather than the pixmap merely existing.
        assert painted_pixels(pixmap) > 20


def test_each_combination_looks_different() -> None:
    QApplication.instance() or QApplication([])
    drawn = [sort_icon(key, desc, 16, COLOR).toImage() for key, desc in COMBINATIONS]
    for first in range(len(drawn)):
        for second in range(first + 1, len(drawn)):
            assert drawn[first] != drawn[second]


def test_an_unknown_field_still_draws(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    fallback = sort_icon("nonsense", False, 16, COLOR)
    assert fallback.toImage() == sort_icon(SORT_NAME, False, 16, COLOR).toImage()


def test_the_same_request_is_only_drawn_once() -> None:
    QApplication.instance() or QApplication([])
    first = sort_icon(SORT_CREATED, True, 18, COLOR)
    assert sort_icon(SORT_CREATED, True, 18, COLOR).cacheKey() == first.cacheKey()


def test_the_icon_sits_left_of_the_dates(tmp_path: Path, monkeypatch) -> None:
    Image.new("RGB", (16, 12), "teal").save(tmp_path / "a.png")
    window = make_window(monkeypatch)
    window.resize(900, 600)
    window.show()
    try:
        window.open_path(tmp_path / "a.png")
        QApplication.processEvents()
        bar = window.statusBar()
        icon_x = window.sort_icon_label.mapTo(bar, window.sort_icon_label.rect().topLeft()).x()
        dates_x = window.file_times_label.mapTo(bar, window.file_times_label.rect().topLeft()).x()
        assert icon_x < dates_x
        assert not window.sort_icon_label.pixmap().isNull()
    finally:
        window.close()


def test_the_icon_and_its_tooltip_follow_the_order(tmp_path: Path, monkeypatch) -> None:
    Image.new("RGB", (16, 12), "teal").save(tmp_path / "a.png")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "a.png")
        label = window.sort_icon_label
        before = label.pixmap().toImage()
        assert "ファイル・フォルダ名" in label.toolTip()
        assert "昇順" in label.toolTip()

        window.choose_sort_key(SORT_MODIFIED)
        assert label.pixmap().toImage() != before
        assert "更新日時" in label.toolTip()

        after_field = label.pixmap().toImage()
        window.sort_descending_action.setChecked(True)
        assert label.pixmap().toImage() != after_field
        assert "降順" in label.toolTip()
    finally:
        window.close()


def test_a_restored_order_is_marked_from_the_start(tmp_path: Path, monkeypatch) -> None:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    monkeypatch.setattr(
        app_module,
        "load_settings",
        lambda: ViewerSettings(sort_key=SORT_CREATED, sort_descending=True),
    )
    window = app_module.MainWindow()
    try:
        # The mark is set up with the status bar, so it is right before any
        # folder has been opened.
        assert "作成日時" in window.sort_icon_label.toolTip()
        assert "降順" in window.sort_icon_label.toolTip()
        expected = sort_icon(SORT_CREATED, True, window.sort_icon_label.fontMetrics().height(),
                             "#98A2B3", window.devicePixelRatioF())
        assert window.sort_icon_label.pixmap().toImage() == expected.toImage()
    finally:
        window.close()
