"""Read the text in the picture on screen.

The reading is done by glyph-ocr, the user's own offline library (RapidOCR on
ONNX Runtime with a Japanese model): the OCR built into Windows, used first,
dropped the dakuten off kana (まだ read as また) too often to be of use.
Nothing leaves the machine. Where the library or its model files are missing,
available() is False and the app simply does not offer the feature, so a
build without them still runs.

The Windows reader is kept below (recognize_with_windows) but nothing calls
it: it read vertical text in better order, and which of the two stays is
still to be settled on real pages.

Only ever run on request, for the one picture on screen: it is not part of
showing a page.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from local_media_viewer.i18n import tr
from local_media_viewer.settings import settings_path

# A gap between two words wider than this share of the line's thickness is a
# real space. English words sit about 0.25-0.3 apart; the pieces Windows cuts
# "1,980" into sit almost touching.
SPACE_GAP = 0.15
# What a space may follow and what it may come before, besides letters and
# digits. Windows splits "1,980" into "1" "," "980" with a visible gap before
# the comma; no space goes there, while "dog. The" and "価格: 1,980" keep theirs.
CLOSING = ".,;:!?)]}\"'"
OPENING = "([{\"'"
# The folder holding glyph-ocr's three model files: inside a frozen build if
# they were bundled, else beside the settings file.
MODELS_FOLDER = "ocr-models"
OCR_THREADS = 2


class TextLine(NamedTuple):
    """One recognised line and the four corners of where it stands, in the
    pixels of the picture that was handed to recognize()."""

    text: str
    quad: tuple[tuple[float, float], ...]


class Reading(NamedTuple):
    text: str
    # Empty from a reader that reports no positions.
    lines: tuple[TextLine, ...] = ()


class Word(NamedTuple):
    text: str
    x: float
    y: float
    width: float
    height: float


def is_cjk(character: str) -> bool:
    """Japanese, Chinese or Korean script, which is written without spaces."""
    code = ord(character)
    return (
        0x3000 <= code <= 0x30FF  # CJK punctuation, hiragana, katakana
        or 0x3400 <= code <= 0x4DBF  # kanji, extension A
        or 0x4E00 <= code <= 0x9FFF  # kanji
        or 0xAC00 <= code <= 0xD7AF  # hangul
        or 0xF900 <= code <= 0xFAFF  # compatibility kanji
        or 0xFF00 <= code <= 0xFFEF  # full-width forms
    )


def join_words(words: Sequence[Word]) -> str:
    """Put one line's words back together with spaces only where they belong.

    Windows reports every Japanese character as a word of its own, so its own
    line text reads "吾 輩 は 猫". A space is kept only between two words that
    are both in a spaced script, really stand apart on the page, and meet at
    characters a space is written between.
    """
    if not words:
        return ""
    left = min(word.x for word in words)
    top = min(word.y for word in words)
    right = max(word.x + word.width for word in words)
    bottom = max(word.y + word.height for word in words)
    # A line of vertical writing is taller than wide, and runs downwards.
    vertical = len(words) > 1 and (bottom - top) > (right - left)
    text = words[0].text
    for previous, word in zip(words, words[1:], strict=False):
        if not previous.text or not word.text:
            text += word.text
            continue
        if vertical:
            gap = word.y - (previous.y + previous.height)
            thickness = max(previous.width, word.width)
        else:
            gap = word.x - (previous.x + previous.width)
            thickness = max(previous.height, word.height)
        before, after = previous.text[-1], word.text[0]
        spaced = (
            not is_cjk(before)
            and not is_cjk(after)
            and (before.isalnum() or before in CLOSING)
            and (after.isalnum() or after in OPENING)
            # "1," then "980" is one number, however far apart it was cut.
            and not (before in ",." and after.isdigit() and text[-2:-1].isdigit())
        )
        text += (" " if spaced and gap > thickness * SPACE_GAP else "") + word.text
    return text


def join_lines(lines: Sequence[Sequence[Word]]) -> str:
    return "\n".join(line for line in (join_words(words) for words in lines) if line)


def model_directory() -> Path | None:
    """Where the model files are, or None when no candidate folder has them."""
    try:
        from glyph_ocr.models import SPECS
    except ImportError:
        return None
    candidates = [settings_path().parent / MODELS_FOLDER]
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidates.insert(0, Path(bundled) / MODELS_FOLDER)
    for folder in candidates:
        # Presence only: the library checks the hashes itself when it loads
        # them, and hashing 14 MB here would be paid on every start.
        if all((folder / name).is_file() for _stage, name, _sha256 in SPECS.values()):
            return folder
    return None


@cache
def engine():
    """The glyph-ocr engine, or None where the library or its models are missing.

    Building it loads nothing: the models are read on the first recognize().
    """
    folder = model_directory()
    if folder is None:
        return None
    try:
        from glyph_ocr import OcrEngine

        return OcrEngine(model_dir=folder, threads=OCR_THREADS)
    except (ImportError, OSError, ValueError):
        return None


def available() -> bool:
    return engine() is not None


def recognize(image: QImage) -> Reading:
    """The text in a picture, one recognised line per line, and where each is.

    Raises when it cannot be read at all (models damaged, picture refused).
    Not for the UI thread: the first call loads the models and every call
    takes around a second. Reader calls it from its worker.
    """
    reader = engine()
    if reader is None or image.isNull():
        raise OSError("OCR is not available")
    from glyph_ocr.engine import MAX_PIXELS
    from glyph_ocr.qt import qimage_to_pil

    pixels = image.width() * image.height()
    full_width = image.width()
    if pixels > MAX_PIXELS:
        # The library refuses anything larger; a spread of two big scans is.
        scale = (MAX_PIXELS / pixels) ** 0.5
        image = image.scaled(
            int(image.width() * scale),
            int(image.height() * scale),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    result = reader.recognize(qimage_to_pil(image))
    # Positions come back in the pixels of what was read; the caller draws
    # them over the picture it handed in, shrunk or not.
    back = full_width / image.width()
    return Reading(
        result.text,
        tuple(
            TextLine(line.text, tuple((x * back, y * back) for x, y in line.quad))
            for line in result.lines
        ),
    )


@cache
def windows_engine():
    """The Windows OCR engine for the user's own languages, or None."""
    if sys.platform != "win32":
        return None
    try:
        # Not at the top of the module: these exist only on Windows.
        from winrt.windows.media.ocr import OcrEngine

        return OcrEngine.try_create_from_user_profile_languages()
    except (ImportError, OSError):
        return None


def recognize_with_windows(image: QImage) -> str:
    """The same reading by Windows' own OCR. Not in use; see the module note.

    Raises OSError when Windows cannot read it at all. Not for the UI
    thread: it waits for Windows, and Windows refuses to let a thread that
    runs a message loop do that ("Cannot call blocking method from
    single-threaded apartment").
    """
    reader = windows_engine()
    if reader is None or image.isNull():
        raise OSError("OCR is not available")
    from winrt.windows.graphics.imaging import (
        BitmapAlphaMode,
        BitmapPixelFormat,
        SoftwareBitmap,
    )
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    # Windows refuses anything larger than this on either side.
    limit = int(OcrEngine.max_image_dimension)
    if max(image.width(), image.height()) > limit:
        image = image.scaled(
            limit,
            limit,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    # Qt's premultiplied ARGB32 is, byte for byte, the BGRA8 Windows wants.
    image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    width, height = image.width(), image.height()
    row = width * 4
    pixels = bytes(image.constBits())
    if image.bytesPerLine() != row:
        stride = image.bytesPerLine()
        pixels = b"".join(pixels[y * stride : y * stride + row] for y in range(height))
    writer = DataWriter()
    writer.write_bytes(pixels)
    bitmap = SoftwareBitmap.create_copy_with_alpha_from_buffer(
        writer.detach_buffer(),
        BitmapPixelFormat.BGRA8,
        width,
        height,
        BitmapAlphaMode.PREMULTIPLIED,
    )
    # Blocking is fine: this runs on the Reader's worker thread.
    result = reader.recognize_async(bitmap).get()
    return join_lines(
        [
            [
                Word(
                    word.text,
                    word.bounding_rect.x,
                    word.bounding_rect.y,
                    word.bounding_rect.width,
                    word.bounding_rect.height,
                )
                for word in line.words
            ]
            for line in result.lines
        ]
    )


class Reader(QObject):
    """Runs recognize() off the UI thread, one picture at a time.

    `ready` carries the request's generation and the Reading, or None when the
    picture could not be read. As with Enhancer, a request is dropped once
    cancel() or a newer request bumps the generation, so a result never lands
    on a page it was not read from.
    """

    ready = Signal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
        self.generation = 0
        self.closed = False

    def request(self, image: QImage) -> int:
        self.generation += 1
        if not self.closed:
            self._executor.submit(self._work, self.generation, image)
        return self.generation

    def cancel(self) -> None:
        self.generation += 1

    def _work(self, generation: int, image: QImage) -> None:
        if generation != self.generation:
            return
        try:
            reading = recognize(image)
            if isinstance(reading, str):
                # A reader that gives the text alone (the Windows one does).
                reading = Reading(reading)
        except Exception:  # noqa: BLE001 - the backends raise their own types; any failure is "unreadable"
            reading = None
        if generation == self.generation and not self.closed:
            # Queued across threads by Qt, so the result lands on the UI thread.
            self.ready.emit(generation, reading)

    def close(self) -> None:
        # Waits for a picture already in hand: destroying a QObject while a
        # worker is still inside it crashes (see ThumbnailLoader.close()).
        self.closed = True
        self.generation += 1
        self._executor.shutdown(wait=True, cancel_futures=True)
        reader = engine()
        if reader is not None:
            # After the worker is done with it; lets go of the loaded models.
            reader.close()


class TextDialog(QDialog):
    """Shows what was read, to select, correct and copy.

    Not modal and kept open: reading the next page replaces the text, so a
    run of pages can be read without reopening anything.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.resize(520, 420)
        self.source = QLabel()
        self.source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.editor = QPlainTextEdit()
        self.copied = QLabel()
        # Whether the reading is also drawn over the picture. Here, beside
        # the text, because the boxes hide the lettering they report and are
        # switched off and on while the two are compared.
        self.overlay_box = QCheckBox()
        self.copy_button = QPushButton()
        self.copy_button.clicked.connect(self.copy_all)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addWidget(self.overlay_box)
        buttons.addStretch(1)
        buttons.addWidget(self.copied)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.source)
        layout.addWidget(self.editor, 1)
        layout.addLayout(buttons)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(tr("読み取った文字"))
        self.overlay_box.setText(tr("画像に重ねて表示"))
        self.copy_button.setText(tr("すべてコピー"))
        self.close_button.setText(tr("閉じる"))
        self.copied.clear()

    def show_text(self, name: str, text: str) -> None:
        self.source.setText(name)
        self.editor.setPlainText(text)
        self.copied.clear()
        self.show()
        self.raise_()

    def copy_all(self) -> None:
        # The editor's text, not what was read: corrections typed here count.
        QGuiApplication.clipboard().setText(self.editor.toPlainText())
        self.copied.setText(tr("コピーしました"))
