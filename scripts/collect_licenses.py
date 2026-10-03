"""Write the license notices of everything a build bundles into one text file.

    python scripts/collect_licenses.py build/THIRD-PARTY-NOTICES.txt

The packaged app carries the Python runtime, Qt, the OCR stack and the OCR
models, and their licenses ask that their notices go along with them. The
list is worked out from what is installed for the build: the app's direct
dependencies and everything they pull in, each with the license files its
package ships. Run in the build's own environment, so a dependency that is
not installed there (the OCR stack on an Intel Mac) is simply left out.
"""

from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# What the app imports itself. Everything they require comes along.
ROOTS = [
    "PySide6",
    "Pillow",
    "pi-heif",
    "glyph-ocr",
    "winrt-runtime",
    "winrt-Windows.Foundation",
    "winrt-Windows.Foundation.Collections",
    "winrt-Windows.Globalization",
    "winrt-Windows.Graphics.Imaging",
    "winrt-Windows.Media.Ocr",
    "winrt-Windows.Storage.Streams",
]
MODEL_NOTICES = [
    ROOT / "vendor" / "ocr-models" / "NOTICE.txt",
    ROOT / "vendor" / "ocr-models" / "LICENSE-Apache-2.0.txt",
]
# A file is a license notice by its name, wherever in the package it sits:
# dist-info/licenses/LICENSE, cv2/LICENSE-3RD-PARTY.txt and the like.
NOTICE_NAME = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)
REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
# Qt for Python is used under the LGPL, but its wheels ship only a note about
# Qt's commercial license; the LGPL (and the GPL it builds on) are added here.
GNU_TEXTS = [
    ROOT / "scripts" / "licenses" / "LGPL-3.0.txt",
    ROOT / "scripts" / "licenses" / "GPL-3.0.txt",
]
SOURCE = "https://github.com/Hiro-Naka-ops/local-media-viewer"
INTRODUCTION = f"""\
Local Media Viewer bundles the software listed below. Each is distributed
under its own license, reproduced here as shipped by its authors.

Qt for Python (PySide6, shiboken6) and the Qt libraries it contains are used
under the GNU Lesser General Public License version 3; so is FFmpeg where
OpenCV carries it. Both licenses are reproduced at the end of this file. The
complete source of Local Media Viewer, with the scripts that build it, is at
{SOURCE}, so the app can be rebuilt against a modified
version of any of these libraries. Qt's source is at https://download.qt.io/
and https://code.qt.io/, PySide6's at https://code.qt.io/pyside/pyside-setup.git.
"""
RULE = "=" * 78


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def installed(name: str) -> metadata.Distribution | None:
    try:
        return metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None


def bundled_distributions() -> list[metadata.Distribution]:
    """The roots that are installed, and what they require, transitively."""
    found: dict[str, metadata.Distribution] = {}
    pending = list(ROOTS)
    while pending:
        name = pending.pop()
        key = normalized(name)
        if key in found:
            continue
        distribution = installed(name)
        if distribution is None:
            # Not part of this build (another platform's, or an extra).
            continue
        found[key] = distribution
        for requirement in distribution.requires or []:
            if "extra ==" in requirement:
                continue
            match = REQUIREMENT_NAME.match(requirement)
            if match:
                pending.append(match.group(1))
    return sorted(found.values(), key=lambda d: normalized(d.metadata["Name"]))


def notice_files(distribution: metadata.Distribution) -> list[Path]:
    files = []
    for file in distribution.files or []:
        if NOTICE_NAME.search(file.name) and not file.name.endswith((".py", ".pyc", ".pyi")):
            path = Path(distribution.locate_file(file))
            if path.is_file():
                files.append(path)
    return sorted(set(files))


def declared_license(distribution: metadata.Distribution) -> str:
    fields = distribution.metadata
    expression = fields.get("License-Expression")
    if expression:
        return expression
    text = (fields.get("License") or "").strip()
    if text and len(text) < 200:
        return text
    classifiers = [
        c.split("::")[-1].strip() for c in fields.get_all("Classifier") or [] if "License" in c
    ]
    return ", ".join(classifiers) or "see the files below"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def section(title: str, body: str) -> str:
    return f"{RULE}\n{title}\n{RULE}\n\n{body}\n"


def build_notices() -> str:
    parts = [INTRODUCTION]
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        python_license = Path(sys.base_prefix) / "LICENSE"
    if python_license.is_file():
        parts.append(section(f"Python {sys.version.split()[0]}", read(python_license)))
    for path in MODEL_NOTICES:
        if path.is_file() and installed("glyph-ocr") is not None:
            parts.append(section(f"OCR models: {path.name}", read(path)))
    for distribution in bundled_distributions():
        name = distribution.metadata["Name"]
        version = distribution.version
        body = [f"License: {declared_license(distribution)}"]
        home = distribution.metadata.get("Home-page") or next(
            (url.split(",", 1)[-1].strip() for url in distribution.metadata.get_all("Project-URL") or []),
            "",
        )
        if home:
            body.append(f"Home: {home}")
        for path in notice_files(distribution):
            body.append(f"\n--- {path.name} ---\n\n{read(path)}")
        parts.append(section(f"{name} {version}", "\n".join(body)))
    for path in GNU_TEXTS:
        parts.append(section(path.stem, read(path)))
    return "\n".join(parts)


def main(arguments: list[str]) -> None:
    if len(arguments) != 1:
        raise SystemExit("usage: collect_licenses.py <output file>")
    target = Path(arguments[0])
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="": the same bytes on every platform the build runs on.
    with open(target, "w", encoding="utf-8", newline="") as handle:
        handle.write(build_notices())
    print(f"Wrote {target}")


if __name__ == "__main__":
    main(sys.argv[1:])
