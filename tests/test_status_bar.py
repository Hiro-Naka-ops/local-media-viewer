import os
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox

import local_media_viewer.app as app_module
from local_media_viewer.app import format_file_time
from local_media_viewer.media import file_times
from local_media_viewer.settings import ViewerSettings


def save_page(path: Path) -> None:
    Image.new("RGB", (16, 12), "teal").save(path)


def make_window(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No
    )
    return app_module.MainWindow()


def test_file_times_reads_both_stamps(tmp_path: Path) -> None:
    path = tmp_path / "a.png"
    save_page(path)
    os.utime(path, (4000, 4000))
    times = file_times(path)
    assert times is not None
    created, modified = times
    assert modified == 4000
    assert created > 0


def test_file_times_gives_up_quietly_on_a_missing_file(tmp_path: Path) -> None:
    assert file_times(tmp_path / "gone.png") is None


def test_the_status_bar_shows_both_dates(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "a.png"
    save_page(path)
    os.utime(path, (4000, 4000))

    window = make_window(monkeypatch)
    try:
        window.open_path(path)
        shown = window.file_times_label.text()
        assert "作成" in shown
        assert f"更新 {format_file_time(4000)}" in shown
    finally:
        window.close()


def test_the_dates_follow_the_page(tmp_path: Path, monkeypatch) -> None:
    for index, when in enumerate((1000, 90000000)):
        path = tmp_path / f"{index}.png"
        save_page(path)
        os.utime(path, (when, when))

    window = make_window(monkeypatch)
    try:
        window.open_folder(tmp_path, 0)
        assert format_file_time(1000) in window.file_times_label.text()
        window.navigate(1)
        assert format_file_time(90000000) in window.file_times_label.text()
    finally:
        window.close()


def test_a_passing_message_does_not_wipe_the_dates(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "a.png"
    save_page(path)

    window = make_window(monkeypatch)
    try:
        window.open_path(path)
        before = window.file_times_label.text()
        assert before
        # Registering a favourite posts a timed message; a permanent widget is
        # used for the dates so those messages cannot overwrite them.
        window.add_favorite()
        assert "お気に入りに登録しました" in window.statusBar().currentMessage()
        assert window.file_times_label.text() == before
    finally:
        window.close()


def test_the_dates_sit_at_the_right_hand_end(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "a.png"
    save_page(path)

    window = make_window(monkeypatch)
    window.resize(900, 600)
    window.show()
    try:
        window.open_path(path)
        QApplication.processEvents()
        label = window.file_times_label
        bar = window.statusBar()
        # Past the middle of the bar, which is what "bottom right" means here.
        assert label.mapTo(bar, label.rect().topLeft()).x() > bar.width() // 2
    finally:
        window.close()


def test_full_screen_takes_the_dates_away_with_the_status_bar(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "a.png"
    save_page(path)

    window = make_window(monkeypatch)
    window.show()
    QApplication.processEvents()
    try:
        window.open_path(path)
        assert window.statusBar().isVisible()

        window.toggle_fullscreen()
        QApplication.processEvents()
        assert window.statusBar().isVisible() is False
        assert window.file_times_label.isVisible() is False

        window.toggle_fullscreen()
        QApplication.processEvents()
        assert window.statusBar().isVisible()
        assert window.file_times_label.text()
    finally:
        window.close()


def test_the_spread_reports_the_dates_of_the_page_it_names(
    tmp_path: Path, monkeypatch
) -> None:
    for index, when in enumerate((1000, 90000000, 5000, 6000)):
        path = tmp_path / f"{index}.png"
        save_page(path)
        os.utime(path, (when, when))

    window = make_window(monkeypatch)
    try:
        window.open_folder(tmp_path, 0)
        window.spread_action.setChecked(True)
        window.navigate(1)
        assert window.displayed_pages == [1, 2]
        # The status line names page 2's path, so the dates must be its own.
        assert str(tmp_path / "1.png") in window.statusBar().currentMessage()
        assert format_file_time(90000000) in window.file_times_label.text()
    finally:
        window.close()
