# PyInstaller hook for RapidOCR, the engine under glyph-ocr.
#
# RapidOCR reads its config.yaml and default_models.yaml at run time, so its
# data files are needed, but not the 16 MB of Chinese models its package
# carries: glyph-ocr always hands it the Japanese set bundled from
# vendor/ocr-models.
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("rapidocr", excludes=["**/*.onnx"])
