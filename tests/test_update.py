import hashlib
import importlib.util
import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import local_media_viewer.app as app_module
from local_media_viewer import __release_date__, __version__, update
from local_media_viewer.settings import ViewerSettings

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = b"new executable " * 4096
SHA256 = hashlib.sha256(PAYLOAD).hexdigest()
DOWNLOAD = f"{update.DOWNLOAD_PREFIX}v9.0.0/{update.WINDOWS_ASSET}"


def release_data(**changes) -> dict:
    asset = {
        "name": update.WINDOWS_ASSET,
        "browser_download_url": DOWNLOAD,
        "digest": f"sha256:{SHA256}",
    }
    asset.update(changes.pop("asset", {}))
    data = {
        "tag_name": "v9.0.0",
        "html_url": f"{update.PAGE_PREFIX}tag/v9.0.0",
        "assets": [{"name": "Local-Media-Viewer-macOS-arm64.zip"}, asset],
    }
    data.update(changes)
    return data


def make_window(monkeypatch) -> app_module.MainWindow:
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(app_module, "load_settings", ViewerSettings)
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    return app_module.MainWindow()


def wait_for(condition, seconds: float = 10.0) -> None:
    app = QApplication.instance()
    deadline = monotonic() + seconds
    while not condition():
        assert monotonic() < deadline, "timed out"
        app.processEvents()


@pytest.fixture
def server():
    """A local stand-in for GitHub; `pages` maps a path to the bytes it serves."""
    pages: dict[str, bytes] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = pages.get(self.path)
            self.send_response(404 if body is None else 200)
            self.send_header("Content-Length", str(len(body or b"")))
            self.end_headers()
            self.wfile.write(body or b"")

        def log_message(self, *_args) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    httpd.pages = pages
    httpd.url = f"http://127.0.0.1:{httpd.server_port}"
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def make_updater() -> tuple[update.Updater, dict[str, list]]:
    QApplication.instance() or QApplication([])
    updater = update.Updater()
    seen: dict[str, list] = {name: [] for name in ("checked", "check_failed", "downloaded", "download_failed")}
    for name, values in seen.items():
        getattr(updater, name).connect(values.append)
    return updater, seen


def test_versions_compare_by_number_not_by_text() -> None:
    assert update.parse_version("v1.10.0") == (1, 10, 0)
    assert update.parse_version("1.2.3") == (1, 2, 3)
    assert update.parse_version("1.2") is None
    assert update.parse_version(None) is None
    assert update.is_newer("1.10.0", "1.9.0")
    assert not update.is_newer("1.2.0", "1.2.0")
    assert not update.is_newer("1.1.9", "1.2.0")
    # An answer that makes no sense is never an update.
    assert not update.is_newer("latest", "1.2.0")


def test_the_version_in_the_source_is_one_the_updater_can_compare() -> None:
    assert update.parse_version(__version__) is not None


def test_a_release_gives_its_version_page_and_checked_download() -> None:
    release = update.release_from_data(release_data())
    assert release == update.Release("9.0.0", f"{update.PAGE_PREFIX}tag/v9.0.0", DOWNLOAD, SHA256)


def test_an_exe_that_cannot_be_verified_is_not_offered_for_install() -> None:
    assert update.release_from_data(release_data(asset={"digest": None})).download == ""
    assert update.release_from_data(release_data(asset={"digest": "md5:abc"})).download == ""
    elsewhere = release_data(asset={"browser_download_url": "https://example.com/a.exe"})
    assert update.release_from_data(elsewhere).download == ""
    assert update.release_from_data(release_data(assets=[])).download == ""


def test_a_page_outside_the_repository_is_replaced_by_the_releases_page() -> None:
    release = update.release_from_data(release_data(html_url="https://example.com/"))
    assert release.page == update.RELEASES_PAGE


def test_an_answer_that_is_not_a_release_is_rejected() -> None:
    for data in ([], {"message": "Not Found"}, {"tag_name": "nightly"}):
        with pytest.raises(ValueError):
            update.release_from_data(data)


def test_install_swaps_the_exe_and_keeps_the_old_one_aside(tmp_path: Path) -> None:
    executable = tmp_path / "Viewer.exe"
    executable.write_bytes(b"old")
    new = update.staging_path(executable)
    new.write_bytes(b"new")
    # Left by an earlier update that was never cleaned up.
    (tmp_path / "Viewer.exe.old").write_bytes(b"older")

    update.install(new, executable)

    assert executable.read_bytes() == b"new"
    assert (tmp_path / "Viewer.exe.old").read_bytes() == b"old"
    assert not new.exists()

    update.remove_leftovers(executable)
    assert [path.name for path in tmp_path.iterdir()] == ["Viewer.exe"]


def test_a_failed_swap_puts_the_running_exe_back(tmp_path: Path) -> None:
    executable = tmp_path / "Viewer.exe"
    executable.write_bytes(b"old")

    with pytest.raises(OSError):
        update.install(tmp_path / "missing.new", executable)

    assert executable.read_bytes() == b"old"


def test_check_reports_the_latest_release(server) -> None:
    server.pages["/latest"] = json.dumps(release_data()).encode()
    updater, seen = make_updater()
    updater.latest_url = f"{server.url}/latest"

    updater.check()
    assert updater.busy
    wait_for(lambda: seen["checked"])

    assert seen["checked"][0].version == "9.0.0"
    assert not updater.busy


def test_check_reports_a_failure_instead_of_a_release(server) -> None:
    server.pages["/latest"] = b"<html>not json</html>"
    updater, seen = make_updater()

    updater.latest_url = f"{server.url}/latest"
    updater.check()
    wait_for(lambda: seen["check_failed"])
    assert seen["check_failed"] == ["更新情報を読み取れませんでした"]

    updater.latest_url = f"{server.url}/missing"
    updater.check()
    wait_for(lambda: len(seen["check_failed"]) == 2)
    assert not seen["checked"]


def test_download_writes_the_file_once_the_hash_matches(server, tmp_path: Path) -> None:
    server.pages["/app.exe"] = PAYLOAD
    updater, seen = make_updater()
    target = tmp_path / "Viewer.exe.new"

    updater.download(update.Release("9.0.0", "", f"{server.url}/app.exe", SHA256), target)
    wait_for(lambda: seen["downloaded"])

    assert seen["downloaded"] == [target]
    assert target.read_bytes() == PAYLOAD


def test_a_download_with_the_wrong_hash_is_thrown_away(server, tmp_path: Path) -> None:
    server.pages["/app.exe"] = PAYLOAD + b"tampered"
    updater, seen = make_updater()
    target = tmp_path / "Viewer.exe.new"

    updater.download(update.Release("9.0.0", "", f"{server.url}/app.exe", SHA256), target)
    wait_for(lambda: seen["download_failed"])

    assert seen["download_failed"] == ["ダウンロードしたファイルが壊れています"]
    assert not seen["downloaded"]
    assert not target.exists()


def test_a_cancelled_download_leaves_nothing_behind(server, tmp_path: Path) -> None:
    server.pages["/app.exe"] = PAYLOAD
    updater, seen = make_updater()
    target = tmp_path / "Viewer.exe.new"

    updater.download(update.Release("9.0.0", "", f"{server.url}/app.exe", SHA256), target)
    updater.cancel()
    QApplication.instance().processEvents()

    assert not target.exists()
    assert not updater.busy
    assert not seen["downloaded"] and not seen["download_failed"]


def test_a_folder_that_cannot_be_written_fails_before_downloading(tmp_path: Path) -> None:
    updater, seen = make_updater()

    updater.download(update.Release("9.0.0", "", "http://127.0.0.1:9/app.exe", SHA256), tmp_path / "no" / "x.new")

    assert len(seen["download_failed"]) == 1
    assert not updater.busy


def test_the_help_menu_offers_the_check_and_nothing_goes_online_unasked(monkeypatch) -> None:
    requests: list[str] = []
    monkeypatch.setattr(update.Updater, "get", lambda _self, url: requests.append(url))
    window = make_window(monkeypatch)
    try:
        assert window.help_menu.title() == "ヘルプ(&H)"
        texts = [a.text() for a in window.help_menu.actions() if not a.isSeparator()]
        assert texts == ["更新を確認…", f"バージョン {__version__}（{__release_date__} 更新）"]
        # Information only, and it follows the language like everything else.
        assert not window.version_action.isEnabled()
        window.language_actions["en"].trigger()
        assert window.version_action.text() == (
            f"Version {__version__} (updated {__release_date__})"
        )
        assert requests == []
    finally:
        window.close()


def test_being_up_to_date_is_said_so(monkeypatch) -> None:
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, _title, text: shown.append(text))
    window = make_window(monkeypatch)
    try:
        window.show_update_check(update.Release(__version__, update.RELEASES_PAGE))
        assert shown == [f"お使いのバージョン {__version__} は最新です。"]
    finally:
        window.close()


def test_a_newer_release_opens_its_page_where_the_app_cannot_swap_itself(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(
        app_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )
    window = make_window(monkeypatch)
    try:
        # The tests run from source, where there is no EXE to replace.
        page = f"{update.PAGE_PREFIX}tag/v999.0.0"
        window.show_update_check(update.Release("999.0.0", page, DOWNLOAD, SHA256))
        assert opened == [page]
        assert not window.updater.busy
    finally:
        window.close()


def test_a_newer_release_is_downloaded_swapped_in_and_started(
    server, tmp_path: Path, monkeypatch
) -> None:
    server.pages["/app.exe"] = PAYLOAD
    executable = tmp_path / "Viewer.exe"
    executable.write_bytes(b"old")
    started: list[Path] = []
    monkeypatch.setattr(update, "can_self_update", lambda: True)
    monkeypatch.setattr(app_module.sys, "executable", str(executable))
    monkeypatch.setattr(update, "relaunch", started.append)
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    window = make_window(monkeypatch)
    try:
        window.show()
        window.show_update_check(
            update.Release("999.0.0", update.RELEASES_PAGE, f"{server.url}/app.exe", SHA256)
        )
        wait_for(lambda: started)

        assert started == [executable]
        assert executable.read_bytes() == PAYLOAD
        assert (tmp_path / "Viewer.exe.old").read_bytes() == b"old"
        assert window.update_progress is None
        assert not window.isVisible()
    finally:
        window.close()


def test_stamping_writes_the_release_version_into_the_source(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("stamp_version", ROOT / "scripts" / "stamp_version.py")
    stamp_version = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stamp_version)
    target = tmp_path / "__init__.py"
    target.write_bytes(b'"""Doc."""\n\n__version__ = "0.1.0"\n')

    stamp_version.stamp(target, stamp_version.TARGETS[0][1], "1.3.0")

    # Still LF: text mode on Windows would have written CRLF.
    assert target.read_bytes() == b'"""Doc."""\n\n__version__ = "1.3.0"\n'
    # A Windows runner checks the sources out with CRLF, which made the
    # release build fail to find the line; the endings are kept as they are.
    target.write_bytes(b'__version__ = "0.1.0"\r\nrest = 1\r\n')
    stamp_version.stamp(target, stamp_version.TARGETS[0][1], "1.3.0")
    assert target.read_bytes() == b'__version__ = "1.3.0"\r\nrest = 1\r\n'

    for path, pattern in stamp_version.TARGETS:
        assert len(stamp_version.re.findall(pattern, path.read_text(encoding="utf-8"), stamp_version.re.M)) == 1


def test_the_release_date_in_the_source_is_a_date_the_stamp_can_replace() -> None:
    date.fromisoformat(__release_date__)
    text = (ROOT / "src" / "local_media_viewer" / "__init__.py").read_text(encoding="utf-8")
    assert text.count(f'__release_date__ = "{__release_date__}"') == 1
