from pathlib import Path
from time import monotonic

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer import ocr
from local_media_viewer.ocr import Word, join_lines, join_words
from local_media_viewer.settings import ViewerSettings


def row(*texts: str, gap: float = 10, size: float = 30) -> list[Word]:
    """Words side by side, each as wide as its text, `gap` apart."""
    words, x = [], 0.0
    for text in texts:
        width = size * len(text) * 0.6
        words.append(Word(text, x, 0, width, size))
        x += width + gap
    return words


def test_japanese_is_joined_without_spaces() -> None:
    # Windows hands back every character as its own word.
    assert join_words(row(*"吾輩は猫である。")) == "吾輩は猫である。"


def test_english_words_keep_their_spaces() -> None:
    assert join_words(row("The", "quick", "fox.", "It", "ran")) == "The quick fox. It ran"


def test_mixed_text_spaces_only_between_latin_words() -> None:
    words = row("Local", "Media", "Viewer", "1.2.0", "を", "公", "開")
    assert join_words(words) == "Local Media Viewer 1.2.0を公開"


def test_pieces_of_one_number_are_put_back_together() -> None:
    # "1,980" arrives as three words with a gap before the comma.
    words = row("価", "格", ":", "1", ",", "980", "円", "(", "税", "込", ")")
    assert join_words(words) == "価格: 1,980円(税込)"


def test_words_that_touch_are_not_spaced() -> None:
    assert join_words(row("ab", "cd", gap=1)) == "abcd"


def test_vertical_lines_run_downwards() -> None:
    column = [Word(text, 100, index * 44, 36, 36) for index, text in enumerate("縦書き")]
    assert join_words(column) == "縦書き"
    # Latin words stacked far apart still read as separate words.
    stacked = [Word("AB", 0, 0, 30, 30), Word("CD", 0, 60, 30, 30)]
    assert join_words(stacked) == "AB CD"


def test_lines_are_kept_apart_and_empty_ones_dropped() -> None:
    assert join_lines([row("ab", "cd"), [], row(*"猫")]) == "ab cd\n猫"
    assert join_words([]) == ""


def make_window(
    monkeypatch, available: bool = True, reads=None, enabled: bool = True
) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    # The feature is switched off in the app for now; these tests keep it working.
    monkeypatch.setattr(app_module, "OCR_ENABLED", enabled)
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    # The same on every machine: no dependence on Windows' OCR languages.
    monkeypatch.setattr(ocr, "available", lambda: available)
    if reads is not None:
        monkeypatch.setattr(ocr, "recognize", reads)
    return app_module.MainWindow()


def make_book(folder: Path) -> None:
    folder.mkdir()
    for number in (1, 2):
        Image.new("RGB", (60, 40), "white").save(folder / f"{number}.png")


def wait_for(condition, seconds: float = 10.0) -> None:
    app = QApplication.instance()
    deadline = monotonic() + seconds
    while not condition():
        assert monotonic() < deadline, "timed out"
        app.processEvents()


def test_reading_shows_the_text_and_copies_it(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    sizes = []

    def reads(image: QImage) -> str:
        sizes.append((image.width(), image.height()))
        return "一行目\nsecond line"

    window = make_window(monkeypatch, reads=reads)
    try:
        window.open_path(tmp_path / "book" / "1.png")
        assert window.ocr_action.isVisible() and window.ocr_action.isEnabled()
        # Read as shown: turned on its side, the picture handed over is too.
        window.rotate_right_action.trigger()
        window.ocr_action.trigger()
        wait_for(lambda: window.ocr_dialog is not None)
        assert sizes == [(40, 60)]
        dialog = window.ocr_dialog
        assert dialog.isVisible()
        assert dialog.editor.toPlainText() == "一行目\nsecond line"
        assert dialog.source.text() == "1.png"

        # A correction typed into the box is what gets copied.
        dialog.editor.setPlainText("一行目")
        dialog.copy_button.click()
        assert QGuiApplication.clipboard().text() == "一行目"
        assert dialog.copied.text() == "コピーしました"
        # The file itself is never changed by any of this.
        assert Image.open(tmp_path / "book" / "1.png").size == (60, 40)
    finally:
        window.close()


def test_a_page_without_text_only_says_so(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch, reads=lambda _image: " \n")
    try:
        window.open_path(tmp_path / "book" / "1.png")
        window.ocr_action.trigger()
        wait_for(lambda: window.statusBar().currentMessage() == "文字が見つかりませんでした")
        assert window.ocr_dialog is None
    finally:
        window.close()


def test_a_failed_reading_is_reported_not_raised(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")

    def reads(_image: QImage) -> str:
        raise RuntimeError("WinRT said no")

    window = make_window(monkeypatch, reads=reads)
    try:
        window.open_path(tmp_path / "book" / "1.png")
        window.ocr_action.trigger()
        wait_for(lambda: window.statusBar().currentMessage() == "文字を読み取れませんでした")
        assert window.ocr_dialog is None
    finally:
        window.close()


def test_a_reading_of_a_page_left_behind_is_dropped(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch, reads=lambda _image: "text of page 1")
    try:
        window.open_path(tmp_path / "book" / "1.png")
        window.ocr_action.trigger()
        # Let the worker finish, so its result is queued for the UI thread,
        # then turn the page before the event loop delivers it.
        window.ocr_reader._executor.submit(lambda: None).result()
        window.navigate(1)
        for _ in range(5):
            QApplication.instance().processEvents()
        assert window.ocr_dialog is None
        assert window.statusBar().currentMessage() != "1行を読み取りました"
    finally:
        window.close()


def test_the_feature_is_not_offered_where_there_is_no_ocr(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch, available=False)
    try:
        window.open_path(tmp_path / "book" / "1.png")
        assert not window.ocr_action.isVisible()
        asked = window.ocr_reader.generation
        window.read_text()
        assert window.ocr_reader.generation == asked
    finally:
        window.close()


def test_the_feature_is_hidden_while_switched_off(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    read = []
    window = make_window(monkeypatch, reads=lambda _image: read.append(1) or "text", enabled=False)
    try:
        window.show()
        window.open_path(tmp_path / "book" / "1.png")
        assert not window.ocr_action.isVisible()
        # Neither the key nor a direct call reads anything.
        QTest.keyClick(window.image_view.viewport(), Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)
        window.read_text()
        window.ocr_reader._executor.submit(lambda: None).result()
        QApplication.instance().processEvents()
        assert read == [] and window.ocr_dialog is None
    finally:
        window.close()


def test_it_is_switched_off_as_shipped() -> None:
    assert app_module.OCR_ENABLED is False


def test_the_key_works_in_full_screen(monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        assert window.ocr_action in window.actions()
    finally:
        window.close()


@pytest.mark.skipif(not ocr.available(), reason="no Windows OCR language on this machine")
def test_windows_really_reads_a_picture() -> None:
    QApplication.instance() or QApplication([])
    image = QImage(900, 160, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setPen(QColor("black"))
    painter.setFont(QFont("Arial", 48))
    painter.drawText(40, 110, "HELLO WORLD 2026")
    painter.end()

    reader = ocr.Reader()
    try:
        results = []
        reader.ready.connect(lambda _generation, text: results.append(text))
        reader.request(image)
        wait_for(lambda: results)
        assert results[0] is not None
        assert "HELLO" in results[0] and "2026" in results[0]
    finally:
        reader.close()
