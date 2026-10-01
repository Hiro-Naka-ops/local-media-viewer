"""Write a release's version and date into the source before it is built.

    python scripts/stamp_version.py v1.3.0

The release workflow runs this with the version typed into "Run workflow", so
the app knows which release it is and "更新を確認…" has something to compare
against, and the Help menu can say which version this is and from when. The
values in the repository are only what a run from source reports.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"v?(\d+\.\d+\.\d+)")
# (file, the line that carries the version). Not anchored at the line's end:
# a Windows runner checks the files out with CRLF, and $ does not match before
# carriage return.
PACKAGE = ROOT / "src" / "local_media_viewer" / "__init__.py"
TARGETS = [
    (PACKAGE, r'^__version__ = "[^"]*"'),
    (ROOT / "pyproject.toml", r'^version = "[^"]*"'),
]
RELEASE_DATE = r'^__release_date__ = "[^"]*"'
# The runner's clock is UTC; a release made in the morning in Japan would
# otherwise carry the day before.
JAPAN = timezone(timedelta(hours=9))


def stamp(path: Path, pattern: str, version: str) -> None:
    # newline="" both ways: the repository keeps LF, and text mode on Windows
    # would turn every line ending into CRLF.
    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()
    line = re.compile(pattern, re.MULTILINE)
    if len(line.findall(text)) != 1:
        raise SystemExit(f"{path}: expected exactly one version line")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(line.sub(lambda match: re.sub(r'"[^"]*"', f'"{version}"', match.group()), text))


def main(arguments: list[str]) -> None:
    match = VERSION.fullmatch(arguments[0]) if len(arguments) == 1 else None
    if match is None:
        raise SystemExit("usage: stamp_version.py v1.2.0")
    for path, pattern in TARGETS:
        stamp(path, pattern, match.group(1))
    released = datetime.now(JAPAN).date().isoformat()
    stamp(PACKAGE, RELEASE_DATE, released)
    print(f"Stamped version {match.group(1)}, released {released}")


if __name__ == "__main__":
    main(sys.argv[1:])
