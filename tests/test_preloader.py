from pathlib import Path
from time import monotonic, sleep

from PIL import Image
from PySide6.QtWidgets import QApplication

from local_media_viewer.preloader import Frame, ImagePreloader


def wait_for_frame(preloader: ImagePreloader, path: Path, plain: bool) -> Frame:
    deadline = monotonic() + 3
    while monotonic() < deadline:
        frame = preloader.take(path, plain)
        if frame is not None:
            return frame
        preloader.preload([path], plain)
        sleep(0.01)
    raise AssertionError("image was not preloaded")


def test_preloader_decodes_a_still_with_qt(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "sample.png"
    Image.new("RGB", (8, 6), "orange").save(path)
    preloader = ImagePreloader(workers=1)
    try:
        frame = wait_for_frame(preloader, path, plain=True)
        # A plain still skips Pillow so the bitmap is never copied between the
        # two libraries just to be handed to the view.
        assert frame.image is None
        assert frame.qimage is not None
        assert (frame.qimage.width(), frame.qimage.height()) == (8, 6)
        frame.close()
    finally:
        preloader.close()


def test_preloader_uses_pillow_when_the_view_needs_it(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "sample.png"
    Image.new("RGB", (8, 6), "orange").save(path)
    preloader = ImagePreloader(workers=1)
    try:
        frame = wait_for_frame(preloader, path, plain=False)
        assert frame.qimage is None
        assert frame.image is not None
        assert frame.image.size == (8, 6)
        frame.close()
    finally:
        preloader.close()


def test_an_animation_always_comes_back_as_a_pillow_image(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "animated.png"
    frames = [Image.new("RGB", (8, 6), color) for color in ("red", "green", "blue")]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=80)
    preloader = ImagePreloader(workers=1)
    try:
        # Qt reports an APNG as a single frame, so asking it would quietly turn
        # the animation into a still; Pillow has to be the one to decide.
        frame = wait_for_frame(preloader, path, plain=True)
        assert frame.qimage is None
        assert frame.image is not None
        assert int(getattr(frame.image, "n_frames", 1)) == 3
        frame.close()
    finally:
        preloader.close()


def test_a_frame_queued_for_the_other_route_is_not_handed_over(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    path = tmp_path / "sample.png"
    Image.new("RGB", (8, 6), "orange").save(path)
    preloader = ImagePreloader(workers=1)
    try:
        frame = wait_for_frame(preloader, path, plain=True)
        frame.close()
        preloader.preload([path], plain=True)
        # A spread turning on mid-flight must not be served the QImage that was
        # queued for the plain route, or the second page would be dropped.
        assert preloader.take(path, plain=False) is None
    finally:
        preloader.close()
