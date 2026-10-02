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
    monkeypatch.setattr(app_module, "OCR_ENABLED", enabled)
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    # The same on every machine: no dependence on the OCR library being installed.
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


def test_it_is_switched_on_as_shipped() -> None:
    assert app_module.OCR_ENABLED is True


def test_it_is_not_offered_without_the_model_files(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("glyph_ocr")
    from glyph_ocr.models import SPECS

    monkeypatch.setattr(ocr, "settings_path", lambda: tmp_path / "settings.json")
    assert ocr.model_directory() is None

    folder = tmp_path / ocr.MODELS_FOLDER
    folder.mkdir()
    names = [name for _stage, name, _sha256 in SPECS.values()]
    for name in names[:-1]:
        (folder / name).write_bytes(b"")
    # One short of the set is still not a set.
    assert ocr.model_directory() is None
    (folder / names[-1]).write_bytes(b"")
    assert ocr.model_directory() == folder


def test_the_key_works_in_full_screen(monkeypatch) -> None:
    window = make_window(monkeypatch)
    try:
        assert window.ocr_action in window.actions()
    finally:
        window.close()


def lettered_picture() -> QImage:
    QApplication.instance() or QApplication([])
    image = QImage(900, 160, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setPen(QColor("black"))
    painter.setFont(QFont("Arial", 48))
    painter.drawText(40, 110, "HELLO WORLD 2026")
    painter.end()
    return image


@pytest.mark.skipif(ocr.windows_engine() is None, reason="no Windows OCR language on this machine")
def test_the_windows_reader_kept_in_reserve_still_reads() -> None:
    from concurrent.futures import ThreadPoolExecutor

    # On a worker, as it would be used: it refuses to wait on the UI thread.
    with ThreadPoolExecutor(max_workers=1) as worker:
        text = worker.submit(ocr.recognize_with_windows, lettered_picture()).result()
    assert "HELLO" in text and "2026" in text


@pytest.mark.skipif(not ocr.available(), reason="glyph-ocr or its models are not installed")
def test_the_library_really_reads_a_picture() -> None:
    image = lettered_picture()

    reader = ocr.Reader()
    try:
        results = []
        reader.ready.connect(lambda _generation, reading: results.append(reading))
        reader.request(image)
        wait_for(lambda: results)
        assert results[0] is not None
        assert "HELLO" in results[0].text and "2026" in results[0].text
        # Where it stands, in the picture's own pixels: the words were drawn
        # from x=40 across the middle of a 900x160 picture.
        (line,) = results[0].lines
        xs = [x for x, _y in line.quad]
        ys = [y for _x, y in line.quad]
        assert 20 <= min(xs) <= 60 and 500 <= max(xs) <= 900
        assert 30 <= min(ys) and max(ys) <= 150
    finally:
        reader.close()


def reading_of_two_lines(_image: QImage) -> ocr.Reading:
    return ocr.Reading(
        "横の行\n縦の行",
        (
            ocr.TextLine("横の行", ((10, 4), (50, 4), (50, 14), (10, 14))),
            ocr.TextLine("縦の行", ((2, 2), (8, 2), (8, 38), (2, 38))),
        ),
    )


def test_the_reading_is_drawn_over_the_picture_and_listed_too(
    tmp_path: Path, monkeypatch
) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch, reads=reading_of_two_lines)
    try:
        window.resize(700, 600)
        window.show()
        window.open_path(tmp_path / "book" / "1.png")
        overlay = window.image_view.text_overlay
        assert overlay.lines == []
        before = window.image_view.grab().toImage()

        window.ocr_action.trigger()
        wait_for(lambda: window.ocr_dialog is not None)

        # Both at once: the list in its window, the boxes on the picture.
        assert window.ocr_dialog.editor.toPlainText() == "横の行\n縦の行"
        assert [text for text, _polygon in overlay.lines] == ["横の行", "縦の行"]
        assert overlay.isVisible()
        assert window.image_view.grab().toImage() != before
        # Positions are the picture's pixels, so the box sits on the same spot
        # of the page whatever the zoom: the picture is 60 wide, the box
        # starts 10 in.
        shown = window.image_view.item.sceneBoundingRect()
        box = overlay.mapToScene(overlay.lines[0][1].boundingRect()).boundingRect()
        assert abs((box.left() - shown.left()) / shown.width() - 10 / 60) < 0.01
        assert abs(box.width() / shown.width() - 40 / 60) < 0.01
        window.image_view.original_size()
        box = overlay.mapToScene(overlay.lines[0][1].boundingRect()).boundingRect()
        shown = window.image_view.item.sceneBoundingRect()
        assert abs(box.width() / shown.width() - 40 / 60) < 0.01
        # Nothing is added to what can be scrolled.
        assert window.image_view.sceneRect() == window.image_view.item.boundingRect()
    finally:
        window.close()


def test_the_overlay_can_be_switched_off_and_goes_with_the_page(
    tmp_path: Path, monkeypatch
) -> None:
    make_book(tmp_path / "book")
    saved: list[ViewerSettings] = []
    window = make_window(monkeypatch, reads=reading_of_two_lines)
    monkeypatch.setattr(app_module, "save_settings", saved.append)
    try:
        window.show()
        window.open_path(tmp_path / "book" / "1.png")
        overlay = window.image_view.text_overlay
        assert window.ocr_overlay_action.isChecked()

        window.ocr_overlay_action.trigger()
        assert saved[-1].ocr_overlay is False
        window.ocr_action.trigger()
        wait_for(lambda: window.ocr_dialog is not None)
        # Held but not shown; ticking the entry again shows this same reading.
        assert not overlay.isVisible() and len(overlay.lines) == 2
        window.ocr_overlay_action.trigger()
        assert overlay.isVisible() and len(overlay.lines) == 2

        # Turned, the picture no longer matches the positions that were read.
        window.rotate_right_action.trigger()
        assert overlay.lines == []

        window.ocr_action.trigger()
        wait_for(lambda: len(overlay.lines) == 2)
        window.navigate(1)
        assert overlay.lines == []
    finally:
        window.close()


def test_a_reader_without_positions_still_fills_the_dialog(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch, reads=lambda _image: "text only")
    try:
        window.open_path(tmp_path / "book" / "1.png")
        window.ocr_action.trigger()
        wait_for(lambda: window.ocr_dialog is not None)
        assert window.ocr_dialog.editor.toPlainText() == "text only"
        assert window.image_view.text_overlay.lines == []
    finally:
        window.close()


def test_the_view_menu_holds_the_ocr_entries_and_right_click_only_the_reading(
    tmp_path: Path, monkeypatch
) -> None:
    make_book(tmp_path / "book")
    shown: list[list] = []

    class RecordingMenu(app_module.QMenu):
        def exec(self, *_args):
            shown.append(self.actions())
            return None

    window = make_window(monkeypatch)
    monkeypatch.setattr(app_module, "QMenu", RecordingMenu)
    try:
        window.open_path(tmp_path / "book" / "1.png")
        assert window.ocr_menu.title() == "文字認識（OCR）"
        assert window.ocr_menu.menuAction() in window.view_menu.actions()
        assert window.ocr_menu.actions() == [window.ocr_action, window.ocr_overlay_action]

        window.show_media_menu(window.pos())
        assert window.ocr_action in shown[-1]
        # Set once, not reached for while reading: not in the right-click menu.
        assert window.ocr_overlay_action not in shown[-1]
    finally:
        window.close()


def test_the_ocr_submenu_is_hidden_where_there_is_no_ocr(monkeypatch) -> None:
    window = make_window(monkeypatch, available=False)
    try:
        assert not window.ocr_menu.menuAction().isVisible()
    finally:
        window.close()


def test_the_toolbar_has_a_button_that_reads_the_page(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch, reads=lambda _image: "text")
    try:
        window.show()
        window.open_path(tmp_path / "book" / "1.png")
        button = window.toolbar.widgetForAction(window.ocr_action)
        assert button is not None and button.isVisible()
        # Short on the button, in full in the menu.
        assert button.text() == "文字認識"
        assert window.ocr_action.text() == "文字を読み取る（OCR）"
        button.click()
        wait_for(lambda: window.ocr_dialog is not None)
        assert window.ocr_dialog.editor.toPlainText() == "text"
    finally:
        window.close()


def test_the_toolbar_button_is_absent_where_there_is_no_ocr(monkeypatch) -> None:
    window = make_window(monkeypatch, available=False)
    try:
        window.show()
        assert not window.toolbar.widgetForAction(window.ocr_action).isVisible()
    finally:
        window.close()



def test_the_result_window_switches_the_overlay_off_and_on(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch, reads=reading_of_two_lines)
    try:
        window.show()
        window.open_path(tmp_path / "book" / "1.png")
        # Nothing about the overlay on the toolbar: it would be there before
        # anything had been read.
        assert window.toolbar.widgetForAction(window.ocr_overlay_action) is None
        window.ocr_action.trigger()
        wait_for(lambda: window.ocr_dialog is not None)
        overlay = window.image_view.text_overlay
        box = window.ocr_dialog.overlay_box
        assert box.text() == "画像に重ねて表示" and box.isChecked()
        # Not modal: the picture can still be scrolled and zoomed beside it.
        assert not window.ocr_dialog.isModal()
        boxed = window.image_view.grab().toImage()

        box.click()
        # Off: the picture as it is, with the reading kept for switching back.
        assert not overlay.isVisible() and len(overlay.lines) == 2
        assert window.image_view.grab().toImage() != boxed
        # The menu entry is the same switch, either way round.
        assert not window.ocr_overlay_action.isChecked()

        window.ocr_overlay_action.trigger()
        assert box.isChecked() and overlay.isVisible()
        assert window.image_view.grab().toImage() == boxed
    finally:
        window.close()


def test_the_result_window_opens_with_the_saved_choice(tmp_path: Path, monkeypatch) -> None:
    make_book(tmp_path / "book")
    window = make_window(monkeypatch, reads=reading_of_two_lines)
    try:
        window.open_path(tmp_path / "book" / "1.png")
        window.ocr_overlay_action.setChecked(False)
        window.ocr_action.trigger()
        wait_for(lambda: window.ocr_dialog is not None)
        assert not window.ocr_dialog.overlay_box.isChecked()
    finally:
        window.close()
