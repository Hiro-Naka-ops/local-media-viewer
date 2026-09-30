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

# --windowed makes a .app bundle. Kept as a folder bundle (no --onefile): a
# one-file app unpacks itself on every launch and macOS discourages it.
"$PYTHON" -m PyInstaller --noconfirm --clean --windowed \
    --name "Local Media Viewer" \
    --osx-bundle-identifier "io.github.local-media-viewer" \
    --icon build/icon-1024.png \
    --paths src \
    --exclude-module numpy \
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
# Prefers the stable local certificate scripts/setup_mac.sh creates: an
# ad-hoc signature (--sign -) is keyed off the binary's own hash, so it
# changes on every rebuild and macOS treats each one as a different app,
# re-asking for every TCC permission again. Falls back to ad hoc only if
# setup hasn't been run (or was run before this existed) so the build still
# works, just with that re-prompting.
CERT_NAME="Local Media Viewer Dev"
if security find-identity -v -p codesigning "$HOME/Library/Keychains/login.keychain-db" 2>/dev/null \
        | grep -q "$CERT_NAME"; then
    codesign --force --deep --sign "$CERT_NAME" "dist/Local Media Viewer.app"
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
