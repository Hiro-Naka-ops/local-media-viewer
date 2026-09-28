"""Teach Pillow to read HEIC / HEIF (iPhone photos) on import.

Qt has no decoder for them on Windows, so every route that shows a picture
falls back to Pillow for these, and this is what lets Pillow read them.
Imported by each module that opens images with Pillow.
"""

try:
    from pillow_heif import register_heif_opener
except ImportError:  # without it a HEIC file fails to open like any unreadable file
    pass
else:
    register_heif_opener()
