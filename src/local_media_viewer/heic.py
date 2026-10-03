"""Teach Pillow to read HEIC / HEIF (iPhone photos) on import.

Qt has no decoder for them on Windows, so every route that shows a picture
falls back to Pillow for these, and this is what lets Pillow read them.
Imported by each module that opens images with Pillow.

pi-heif rather than pillow-heif: the same library and API, decoding only.
pillow-heif also bundles the x265 encoder, which is GPL; an app that only
reads photos has no use for it and should not carry its terms.
"""

try:
    from pi_heif import register_heif_opener
except ImportError:  # without it a HEIC file fails to open like any unreadable file
    pass
else:
    register_heif_opener()
