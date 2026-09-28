#!/bin/sh
# Build "Local Media Viewer.app" and zip it, on a Mac.
# The app runs on Macs with the same CPU as the one that built it
# (arm64 = Apple silicon, x86_64 = Intel), so the zip is named after it.
set -eu
cd "$(dirname "$0")/.."

python3 -m pip install "Pillow==12.1.1" "PySide6==6.10.2" "pyinstaller==6.19.0"

mkdir -p build
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 scripts/render_icon.py build/icon-1024.png

# --windowed makes a .app bundle. Kept as a folder bundle (no --onefile): a
# one-file app unpacks itself on every launch and macOS discourages it.
python3 -m PyInstaller --noconfirm --clean --windowed \
    --name "Local Media Viewer" \
    --osx-bundle-identifier "io.github.local-media-viewer" \
    --icon build/icon-1024.png \
    --paths src \
    --exclude-module numpy \
    run_viewer.pyw

# ditto, not zip: the bundle holds symlinks that zip would turn into copies,
# which breaks the code signature.
ditto -c -k --keepParent "dist/Local Media Viewer.app" \
    "dist/Local-Media-Viewer-macOS-$(uname -m).zip"
echo "Built dist/Local-Media-Viewer-macOS-$(uname -m).zip"
