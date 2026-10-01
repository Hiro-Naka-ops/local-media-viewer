"""Look for a newer release on GitHub and, on Windows, swap the EXE for it.

The one place the app touches the network, and only when the user asks: the
viewer is otherwise fully local, so nothing here runs on its own.

Releases are the ones .github/workflows/build.yml publishes. The request goes
through Qt's network stack rather than urllib: it uses the system's own TLS
certificates (a frozen Mac build has no OpenSSL certificate store to verify
against), and it runs on the UI thread's event loop, so there is no worker
thread to wait for when the window closes mid-download.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from local_media_viewer import __version__
from local_media_viewer.i18n import tr

REPOSITORY = "Hiro-Naka-ops/local-media-viewer"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"
# Anything the release data points at has to live under these, so a tampered
# or mistaken answer cannot send the app, or the browser, somewhere else.
PAGE_PREFIX = f"https://github.com/{REPOSITORY}/releases/"
DOWNLOAD_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
# The asset name build.yml uploads for Windows.
WINDOWS_ASSET = "Local-Media-Viewer.exe"
# Without a User-Agent the GitHub API answers 403.
USER_AGENT = f"Local-Media-Viewer/{__version__}"
# Given up after this long with no data moving, not after this long in total:
# the EXE is tens of megabytes and may take minutes on a slow line.
TIMEOUT_MS = 15_000
NEW_SUFFIX = ".new"
OLD_SUFFIX = ".old"

VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
DIGEST = re.compile(r"sha256:([0-9a-f]{64})")


@dataclass(frozen=True)
class Release:
    """The latest published release, as far as the updater cares."""

    version: str
    page: str
    # Empty when the release has no Windows EXE the app could verify; the
    # update is then left to the download page.
    download: str = ""
    sha256: str = ""


def parse_version(text: object) -> tuple[int, int, int] | None:
    """(1, 2, 0) for "v1.2.0" or "1.2.0", None for anything else."""
    match = VERSION.fullmatch(text.strip()) if isinstance(text, str) else None
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(latest: str, current: str = __version__) -> bool:
    newest, running = parse_version(latest), parse_version(current)
    return newest is not None and running is not None and newest > running


def release_from_data(data: Any) -> Release:
    """Reads GitHub's "latest release" answer. ValueError when it is not one."""
    if not isinstance(data, dict):
        raise ValueError("not a release")
    version = parse_version(data.get("tag_name"))
    if version is None:
        raise ValueError("no version")
    page = data.get("html_url")
    if not isinstance(page, str) or not page.startswith(PAGE_PREFIX):
        page = RELEASES_PAGE
    download = sha256 = ""
    assets = data.get("assets")
    for asset in assets if isinstance(assets, list) else []:
        if not isinstance(asset, dict) or asset.get("name") != WINDOWS_ASSET:
            continue
        url, digest = asset.get("browser_download_url"), asset.get("digest")
        match = DIGEST.fullmatch(digest) if isinstance(digest, str) else None
        # Both or neither: an EXE that cannot be checked is never installed.
        if isinstance(url, str) and url.startswith(DOWNLOAD_PREFIX) and match:
            download, sha256 = url, match.group(1)
    return Release(".".join(map(str, version)), page, download, sha256)


def can_self_update() -> bool:
    """Only the single-file Windows EXE replaces itself.

    Run from source there is no EXE to replace, and the Mac app is unsigned:
    a copy swapped in behind Gatekeeper's back may refuse to start.
    """
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def staging_path(executable: Path) -> Path:
    """Where the download goes: beside the EXE, so the swap is a plain rename
    on one volume, and a folder the app cannot write to fails before the
    download rather than after it."""
    return executable.with_name(executable.name + NEW_SUFFIX)


def install(new: Path, executable: Path) -> None:
    """Puts `new` in the running EXE's place, keeping the old one as *.old.

    Windows will not overwrite or delete an EXE that is running, but it will
    rename one, so the running copy steps aside and is removed on a later
    start (remove_leftovers).
    """
    old = executable.with_name(executable.name + OLD_SUFFIX)
    executable.replace(old)
    try:
        new.replace(executable)
    except OSError:
        # Never leave the app without an EXE under its own name.
        old.replace(executable)
        raise


def remove_leftovers(executable: Path) -> None:
    """Clears what an earlier update, finished or abandoned, left behind."""
    for suffix in (OLD_SUFFIX, NEW_SUFFIX):
        try:
            executable.with_name(executable.name + suffix).unlink(missing_ok=True)
        except OSError:
            # Still held by the copy that is on its way out; the next start
            # gets another go.
            pass


def relaunch(executable: Path) -> None:
    # A PyInstaller EXE started by another one inherits its environment and
    # takes itself for a child of the same run, reusing the unpacked files of
    # the old version; this tells the bootloader to start afresh.
    environment = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    subprocess.Popen([str(executable)], env=environment, close_fds=True)


class Updater(QObject):
    """One request at a time: the check, or the download that follows it.

    A cancelled request reports nothing at all. The slots find their reply
    through sender() rather than a lambda holding it: a reply kept alive by
    its own connection aborted the process once its manager was gone.
    """

    checked = Signal(object)  # Release
    check_failed = Signal(str)
    progress = Signal(int, int)  # bytes so far, bytes in all (0 if unknown)
    downloaded = Signal(object)  # Path
    download_failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.latest_url = LATEST_URL
        self.reply: QNetworkReply | None = None
        self.target: Path | None = None
        self.file = None
        self.hash = hashlib.sha256()
        self.sha256 = ""
        self.write_error = ""

    @property
    def busy(self) -> bool:
        return self.reply is not None

    def get(self, url: str) -> QNetworkReply:
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, USER_AGENT)
        request.setTransferTimeout(TIMEOUT_MS)
        self.reply = self.network.get(request)
        return self.reply

    def check(self) -> None:
        self.cancel()
        self.get(self.latest_url).finished.connect(self.finish_check)

    def finish_check(self) -> None:
        reply = self.sender()
        reply.deleteLater()
        if reply is not self.reply:
            return
        self.reply = None
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.check_failed.emit(reply.errorString())
            return
        try:
            release = release_from_data(json.loads(reply.readAll().data()))
        except ValueError:  # includes text that is not JSON at all
            self.check_failed.emit(tr("更新情報を読み取れませんでした"))
            return
        self.checked.emit(release)

    def download(self, release: Release, target: Path) -> None:
        """Fetches the release's EXE into `target` and checks its SHA-256."""
        self.cancel()
        try:
            self.file = open(target, "wb")
        except OSError as error:
            self.download_failed.emit(str(error))
            return
        self.target = target
        self.hash = hashlib.sha256()
        self.write_error = ""
        self.sha256 = release.sha256
        reply = self.get(release.download)
        # Written as it arrives: the EXE is too large to hold in memory twice.
        reply.readyRead.connect(self.store)
        reply.downloadProgress.connect(self.report)
        reply.finished.connect(self.finish_download)

    def report(self, done: int, total: int) -> None:
        if self.sender() is self.reply:
            self.progress.emit(done, max(total, 0))

    def store(self) -> None:
        reply = self.reply
        if reply is None or self.file is None:
            return
        data = reply.readAll().data()
        try:
            self.file.write(data)
        except OSError as error:  # most likely a full disk
            self.write_error = str(error)
            reply.abort()
            return
        self.hash.update(data)

    def finish_download(self) -> None:
        reply = self.sender()
        reply.deleteLater()
        if reply is not self.reply:
            return
        self.store()
        self.reply = None
        target = self.target
        problem = self.write_error
        try:
            self.file.close()
        except OSError as error:
            problem = problem or str(error)
        self.file = None
        self.target = None
        if not problem and reply.error() != QNetworkReply.NetworkError.NoError:
            problem = reply.errorString()
        if not problem and self.hash.hexdigest() != self.sha256:
            problem = tr("ダウンロードしたファイルが壊れています")
        if problem:
            target.unlink(missing_ok=True)
            self.download_failed.emit(problem)
            return
        self.downloaded.emit(target)

    def cancel(self) -> None:
        """Drops the request in hand, and the half-written download with it."""
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()
        if self.file is not None:
            self.file.close()
            self.file = None
        if self.target is not None:
            try:
                self.target.unlink(missing_ok=True)
            except OSError:
                pass
            self.target = None
