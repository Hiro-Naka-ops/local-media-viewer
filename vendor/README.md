# vendor

このリポジトリと一緒に持ち歩く、PyPI に無いライブラリの配布物です。

## glyph-ocr

文字認識（OCR）のライブラリ。開発元は別プロジェクト（`C:\Users\hirok\codex\glyph-ocr`）で、
そこでビルドした wheel をここへコピーしています。**ここのファイルを直接編集しない**でください。
修正は glyph-ocr 側で行い、版を上げてビルドし、新しい wheel に置き換えます。

入っているのは Python のコードだけです（約 12KB）。次のものは含みません。

- 依存ライブラリ（rapidocr、onnxruntime、opencv、numpy など）: インストール時に PyPI から取得します
- モデル3ファイル（約 14.4MB）: `%LOCALAPPDATA%\LocalMediaViewer\ocr-models`
  （Mac は `~/Library/Application Support/LocalMediaViewer/ocr-models`）に置きます

インストール:

```cmd
py -3.14 -m pip install vendor\glyph_ocr-0.1.2-py3-none-any.whl
```

ライブラリとモデルのどちらかが無い環境では、アプリは OCR のメニューとボタンを出しません（それ以外は普通に動きます）。

### 更新の手順

1. glyph-ocr 側で修正し、`pyproject.toml` の版を上げて `scripts\build_library.py` を実行する
2. できた `dist\glyph_ocr-<版>-py3-none-any.whl` をここへコピーし、古い版をここから消す
   （古い版は glyph-ocr の `dist` に比較用として残っています）
3. 上のコマンドの版を直し、入れ直す
4. `python -m pytest -q` を通す（`tests/test_ocr.py` が、ここの wheel と入っている版の食い違いを検出します）
