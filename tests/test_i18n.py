import ast
import re
import string
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

import local_media_viewer.app as app_module
from local_media_viewer import i18n
from local_media_viewer.i18n import CATALOG, LANGUAGES, resolve, tr
from local_media_viewer.settings import ViewerSettings

SOURCE = Path(__file__).resolve().parents[1] / "src" / "local_media_viewer"
JAPANESE_TEXT = re.compile("[぀-ヿ一-鿿]")


def make_window(monkeypatch, settings: ViewerSettings | None = None) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    saved: list[ViewerSettings] = []
    monkeypatch.setattr(app_module, "load_settings", lambda: settings or ViewerSettings())
    monkeypatch.setattr(app_module, "save_settings", saved.append)
    window = app_module.MainWindow()
    window.saved = saved
    return window


def ui_strings() -> set[str]:
    """Every Japanese string literal in the app, docstrings left out."""
    found: set[str] = set()
    for path in SOURCE.glob("*.py"):
        if path.name == "i18n.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and JAPANESE_TEXT.search(node.value)
            ):
                found.add(node.value)
    return found


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_japanese_string_in_the_app_has_a_translation() -> None:
    missing = ui_strings() - CATALOG.keys()
    assert not missing, f"not in i18n.CATALOG: {sorted(missing)}"


def test_every_entry_covers_every_language_with_the_same_placeholders() -> None:
    others = {code for code, _name in LANGUAGES} - {i18n.JAPANESE}
    for source, translations in CATALOG.items():
        assert translations.keys() == others, source
        for code, text in translations.items():
            assert text.strip(), (source, code)
            assert placeholders(text) == placeholders(source), (source, code)


def test_the_language_follows_the_choice_then_windows_then_english() -> None:
    assert resolve("ko", "ja_JP") == "ko"
    assert resolve("", "ja_JP") == "ja"
    assert resolve("", "zh_CN") == "zh"
    assert resolve("", "en_US") == "en"
    # Nothing supported, or a hand-edited settings file: English.
    assert resolve("", "fr_FR") == "en"
    assert resolve(123, "de_DE") == "en"
    assert resolve("xx", "ko-KR") == "ko"


def test_tr_translates_and_fills_placeholders() -> None:
    assert tr("前へ") == "前へ"
    i18n.set_language("en")
    assert tr("前へ") == "Previous"
    assert tr("お気に入りに登録しました: {name}", name="作品") == "Added to favorites: 作品"
    # Text that is not in the catalog is shown as it is rather than dropped.
    assert tr("未登録") == "未登録"


def test_the_language_menu_can_always_be_read_in_english() -> None:
    for code, _name in LANGUAGES:
        i18n.set_language(code)
        assert "Language" in i18n.language_menu_title()


def test_a_fresh_install_follows_windows(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "system_language", lambda: "ko_KR")
    window = make_window(monkeypatch)
    try:
        assert i18n.current_language() == "ko"
        assert window.open_file_action.text() == "파일 열기…"
        assert window.language_actions[i18n.AUTO].isChecked()
    finally:
        window.close()


def test_switching_language_relabels_the_window_in_place(tmp_path: Path, monkeypatch) -> None:
    Image.new("RGB", (8, 8), "red").save(tmp_path / "1.png")
    window = make_window(monkeypatch)
    try:
        window.open_path(tmp_path / "1.png")
        assert window.open_file_action.text() == "ファイルを開く…"

        window.language_actions["en"].trigger()

        assert window.open_file_action.text() == "Open File…"
        assert window.view_menu.title() == "&View"
        assert window.favorites_menu.title() == "F&avorites"
        assert window.register_favorite_action.text() == "Add to Favorites"
        assert window.spread_action.text() == "Two-Page Spread"
        assert window.effect_menu.title() == "Effect"
        assert window.effect_actions["sepia"].text() == "Sepia"
        assert window.sort_actions["modified"].text() == "Date Modified"
        assert window.filter_title.text() == "Display Filters"
        assert window.file_times_label.text().startswith("Created ")
        assert "Sort order" in window.sort_icon_label.toolTip()
        assert window.language_menu.title() == "Language"
        # The choice is remembered, and only the chosen entry is ticked.
        assert window.saved[-1].language == "en"
        ticked = [code for code, a in window.language_actions.items() if a.isChecked()]
        assert ticked == ["en"]
    finally:
        window.close()


def test_a_saved_language_wins_over_windows(monkeypatch) -> None:
    window = make_window(monkeypatch, ViewerSettings(language="zh"))
    try:
        assert window.open_folder_action.text() == "打开文件夹…"
        assert window.language_actions["zh"].isChecked()
    finally:
        window.close()


def test_right_click_menu_carries_fit_and_full_screen_but_not_language(
    tmp_path: Path, monkeypatch
) -> None:
    Image.new("RGB", (8, 8), "red").save(tmp_path / "1.png")
    shown: list[list] = []

    class RecordingMenu(app_module.QMenu):
        def exec(self, *_args):
            shown.append(self.actions())
            return None

    window = make_window(monkeypatch)
    monkeypatch.setattr(app_module, "QMenu", RecordingMenu)
    try:
        window.open_path(tmp_path / "1.png")
        window.show_media_menu(window.pos())
        actions = shown[-1]
        texts = [a.text() for a in actions if not a.isSeparator()]
        assert texts[:3] == ["お気に入りに登録", "表示サイズ", "全画面表示	Enter"]
        assert window.language_menu.menuAction() not in actions
        for group in window.option_groups:
            assert all(action in actions for action in group)
    finally:
        window.close()
