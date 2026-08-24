from pathlib import Path
from time import monotonic, sleep

from PIL import Image

from local_media_viewer.preloader import ImagePreloader


def wait_for_image(preloader: ImagePreloader, path: Path) -> Image.Image:
    deadline = monotonic() + 3
    while monotonic() < deadline:
        image = preloader.take(path)
        if image is not None:
            return image
        preloader.preload([path])
        sleep(0.01)
    raise AssertionError("image was not preloaded")


def test_preloader_decodes_an_image(tmp_path: Path) -> None:
    path = tmp_path / "sample.png"
    Image.new("RGB", (8, 6), "orange").save(path)
    preloader = ImagePreloader(workers=1)
    try:
        preloader.preload([path])
        loaded = wait_for_image(preloader, path)
        assert loaded.size == (8, 6)
        loaded.close()
    finally:
        preloader.close()
