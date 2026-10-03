#!/bin/sh
# Build "Local Media Viewer.app" and zip it, on a Mac.
# The app runs on Macs with the same CPU as the one that built it
# (arm64 = Apple silicon, x86_64 = Intel), so the zip is named after it.
#
# Needs an environment set up by scripts/setup_mac.sh first (a .venv/ with
# a Python new enough for this project's dependencies) — this script does
# not install anything itself, so the same build works the same way on any
# machine regardless of what its system python3 happens to be.
set -eu
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python3 ]; then
    echo "No .venv/ found. Run scripts/setup_mac.sh first." >&2
    exit 1
fi
PYTHON=.venv/bin/python3

mkdir -p build
QT_QPA_PLATFORM=offscreen PYTHONPATH=src "$PYTHON" scripts/render_icon.py build/icon-1024.png

# The notices of everything bundled (Python, Qt, the OCR stack, the models),
# as their licenses require; they go inside the app.
"$PYTHON" scripts/collect_licenses.py build/THIRD-PARTY-NOTICES.txt

# With the OCR library installed (setup_mac.sh does on Apple silicon), the
# models from vendor/ go in too, and scripts/pyinstaller-hooks keeps
# RapidOCR's unused Chinese models out. Without it (Intel) numpy, which only
# the OCR needs, is left out as before; the app then hides the feature.
if "$PYTHON" -c "import glyph_ocr, rapidocr" 2>/dev/null; then
    set -- --additional-hooks-dir scripts/pyinstaller-hooks --add-data "vendor/ocr-models:ocr-models"
else
    echo "OCR library not installed: building without OCR." >&2
    set -- --exclude-module numpy
fi

# --windowed makes a .app bundle. Kept as a folder bundle (no --onefile): a
# one-file app unpacks itself on every launch and macOS discourages it.
"$PYTHON" -m PyInstaller --noconfirm --clean --windowed \
    --name "Local Media Viewer" \
    --osx-bundle-identifier "io.github.local-media-viewer" \
    --icon build/icon-1024.png \
    --paths src \
    --add-data "build/THIRD-PARTY-NOTICES.txt:." \
    "$@" \
    run_viewer.pyw

# Registers the custom URL scheme the Mac widget (mac-widget/) uses to open a
# favorite by id (see local_media_viewer.mac_widget.URL_SCHEME). PyInstaller's
# CLI has no flag for CFBundleURLTypes, so it is added after the fact.
PLIST="dist/Local Media Viewer.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes array" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0 dict" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLName string io.github.local-media-viewer.widget" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string localmediaviewer" "$PLIST"

# Declares the file types this app opens, so Finder offers it under 「開く」
# / 「このアプリケーションで開く」 (including the 推奨 group in Get Info) for
# images and videos, not just as a last-resort "other application". Kept in
# sync with local_media_viewer.media's own extension lists rather than
# duplicating them here.
PYTHONPATH=src "$PYTHON" - "$PLIST" <<'PYEOF'
import plistlib
import sys
from pathlib import Path

from local_media_viewer.media import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

plist_path = Path(sys.argv[1])
info = plistlib.loads(plist_path.read_bytes())
info["CFBundleDocumentTypes"] = [
    {
        "CFBundleTypeName": "Image",
        "CFBundleTypeRole": "Viewer",
        "LSHandlerRank": "Alternate",
        "LSItemContentTypes": ["public.image"],
        "CFBundleTypeExtensions": sorted(ext.lstrip(".") for ext in IMAGE_EXTENSIONS),
    },
    {
        "CFBundleTypeName": "Movie",
        "CFBundleTypeRole": "Viewer",
        "LSHandlerRank": "Alternate",
        "LSItemContentTypes": ["public.movie"],
        "CFBundleTypeExtensions": sorted(ext.lstrip(".") for ext in VIDEO_EXTENSIONS),
    },
]
plist_path.write_bytes(plistlib.dumps(info))
PYEOF

# PyInstaller already signed the bundle before the Info.plist edits above,
# so the signature no longer matches it ("codesign --verify" would report
# "invalid Info.plist"). Re-sign so it's valid again — otherwise macOS's
# privacy (TCC) checks silently refuse the app access to protected folders
# like Documents/Desktop, or to the widget's shared App Group container,
# with no prompt and no error, because it can't trust who is asking.
#
# Prefers the stable local certificate scripts/setup_mac.sh creates, signed
# with an EXPLICIT designated requirement pinned to that certificate's own
# hash rather than codesign's auto-generated one. codesign's default
# requirement for a self-signed cert (no Apple CA chain backing it) still
# ties itself to the exact binary content, so it changes on every rebuild —
# a version update looks like a brand-new app to macOS and every TCC grant
# (Full Disk Access included) has to be re-approved, even though the same
# certificate signed it. Pinning the requirement to "this certificate +
# this bundle identifier" instead makes any build signed with it count as
# the same app, so a grant survives rebuilds, version bumps included.
# Falls back to ad hoc only if setup hasn't been run (or was run before
# this existed) so the build still works, just with that re-prompting.
CERT_NAME="Local Media Viewer Dev"
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"
if security find-identity -v -p codesigning "$KEYCHAIN" 2>/dev/null | grep -q "$CERT_NAME"; then
    # Pass 1: sign every nested framework/library normally (--deep), each
    # getting its own correct, auto-generated requirement for ITS OWN
    # identifier (Python.framework, PySide6's Qt frameworks, etc. are not
    # "io.github.local-media-viewer" and must not be told they are).
    codesign --force --deep --sign "$CERT_NAME" "dist/Local Media Viewer.app"

    # Pass 2: re-sign ONLY the outer app bundle (no --deep this time) with
    # an explicit requirement pinned to this certificate's own hash rather
    # than codesign's default. The default requirement for a self-signed
    # cert (no Apple CA chain backing it) still ties itself to the exact
    # binary content, so it changes on every rebuild — a version update
    # looks like a brand-new app to macOS and every TCC grant (Full Disk
    # Access included) has to be re-approved, even though the same
    # certificate signed it. Pinning it to "this certificate + this bundle
    # identifier" instead makes any build signed with it count as the same
    # app, so a grant survives rebuilds, version bumps included. Doing this
    # as its own non-deep pass leaves pass 1's nested signatures untouched —
    # applying this top-level-only requirement with --deep would overwrite
    # every nested item with a requirement naming the WRONG identifier for
    # them, which is what broke `codesign --verify` (and real TCC checks)
    # last time.
    CERT_HASH="$(security find-certificate -c "$CERT_NAME" -Z "$KEYCHAIN" 2>/dev/null \
        | awk '/^SHA-1 hash:/{print $NF; exit}')"
    if [ -n "$CERT_HASH" ]; then
        codesign --force --sign "$CERT_NAME" \
            -r "=designated => anchor = H\"$CERT_HASH\" and identifier \"io.github.local-media-viewer\"" \
            "dist/Local Media Viewer.app"
    else
        echo "Found certificate \"$CERT_NAME\" but could not read its hash;" >&2
        echo "leaving the default (unpinned) requirement; prompts may reappear on rebuild." >&2
    fi
else
    echo "No local signing certificate found; run scripts/setup_mac.sh to create one" >&2
    echo "so macOS privacy prompts don't reappear on every rebuild. Signing ad hoc for now." >&2
    codesign --force --deep --sign - "dist/Local Media Viewer.app"
fi

# ditto, not zip: the bundle holds symlinks that zip would turn into copies,
# which breaks the code signature.
ditto -c -k --keepParent "dist/Local Media Viewer.app" \
    "dist/Local-Media-Viewer-macOS-$(uname -m).zip"
echo "Built dist/Local-Media-Viewer-macOS-$(uname -m).zip"
