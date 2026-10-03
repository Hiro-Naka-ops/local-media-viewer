# vendor

このリポジトリと一緒に持ち歩く、PyPI に無いライブラリの配布物です。

## glyph-ocr

文字認識（OCR）のライブラリ。開発元は別プロジェクト（`C:\Users\hirok\codex\glyph-ocr`）で、
そこでビルドした wheel をここへコピーしています。**ここのファイルを直接編集しない**でください。
修正は glyph-ocr 側で行い、版を上げてビルドし、新しい wheel に置き換えます。

入っているのは Python のコードだけです（約 12KB）。依存ライブラリ（rapidocr、onnxruntime、opencv、numpy など）は
インストール時に PyPI から取得します。

## ocr-models

OCR のモデル3ファイル（約 14.4MB）。glyph-ocr の `models` と同じもので、ハッシュは `NOTICE.txt` にあります。
Apache License 2.0 で、全文が `LICENSE-Apache-2.0.txt`、出所と著作権の表示が `NOTICE.txt` です
（再配布するときはこの2つを必ず一緒に渡す）。調べた経緯は glyph-ocr の `docs/model-licenses.md`。

アプリは次の順でモデルを探します。ソースから起動するなら、ライブラリを入れるだけで動きます。

1. ビルドしたアプリの中（`build_windows.cmd` / `build_mac.sh` が同梱する）
2. 設定ファイルの隣の `ocr-models`（Windows は `%LOCALAPPDATA%\LocalMediaViewer\ocr-models`）
3. このフォルダ（`vendor/ocr-models`）

インストール:

```cmd
py -3.14 -m pip install vendor\glyph_ocr-0.1.2-py3-none-any.whl
```

ライブラリとモデルのどちらかが無い環境では、アプリは OCR のメニューとボタンを出しません（それ以外は普通に動きます）。
Intel Mac は OCR の実行部品（ONNX Runtime）に Python 3.14 用が無いので、入れられません（`setup_mac.sh` も入れません）。

### 更新の手順

1. glyph-ocr 側で修正し、`pyproject.toml` の版を上げて `scripts\build_library.py` を実行する
2. できた `dist\glyph_ocr-<版>-py3-none-any.whl` をここへコピーし、古い版をここから消す
   （古い版は glyph-ocr の `dist` に比較用として残っています）
3. 上のコマンドの版を直し、入れ直す
4. `python -m pytest -q` を通す（`tests/test_ocr.py` が、ここの wheel と入っている版の食い違いを検出します）
