# PyInstaller hook for OpenCV, used instead of the standard one for the builds
# (--additional-hooks-dir scripts/pyinstaller-hooks takes precedence over
# pyinstaller-hooks-contrib).
#
# It runs the standard hook unchanged, then drops opencv_videoio_ffmpeg*.dll:
# the FFmpeg plugin OpenCV ships on Windows for reading video files. The OCR
# only hands OpenCV pictures already in memory, and FFmpeg is LGPL, which a
# single-file EXE cannot honour easily (the library has to stay replaceable).
# On macOS FFmpeg is linked into cv2 itself, so nothing is dropped there; the
# app is a folder bundle and its notices list FFmpeg (collect_licenses.py).
import os
import runpy

import _pyinstaller_hooks_contrib

_standard = runpy.run_path(
    os.path.join(os.path.dirname(_pyinstaller_hooks_contrib.__file__), "stdhooks", "hook-cv2.py")
)
globals().update({name: value for name, value in _standard.items() if not name.startswith("__")})
binaries = [
    entry for entry in _standard.get("binaries", [])
    if not os.path.basename(entry[0]).lower().startswith("opencv_videoio_ffmpeg")
]
