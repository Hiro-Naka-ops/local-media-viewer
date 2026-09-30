# Mac ウィジェット (FavoritesWidget) — Python 側との契約

このフォルダは、Xcode の Widget Extension プロジェクト（例: MediaViewerWidgets /
FavoritesWidget）を置く場所です。Python アプリ側（`src/local_media_viewer/mac_widget.py`）が
書き出すデータを読むだけの、読み取り専用のウィジェットとして実装してください。

## App Group

- 識別子: `group.io.github.local-media-viewer`
- Xcode で **MediaViewerWidgets（入れ物アプリ）** と **FavoritesWidget（Widget Extension）** の
  両方のターゲットに、この同じ App Group を Signing & Capabilities から追加してください
  （どちらか片方だけでは共有コンテナが読めません）
- 変更する場合は `src/local_media_viewer/mac_widget.py` の `APP_GROUP_ID` も合わせて変更すること

## 共有コンテナの中身

`~/Library/Group Containers/group.io.github.local-media-viewer/` の下に、Python アプリが
お気に入りが変わるたびに（登録・解除・フォルダ分け）書き出します。起動時にも一度、少し遅れて
書き出されます。

- `favorites.json` — 配列。各要素:
  ```json
  { "id": "abc123...", "name": "表示名", "group": "フォルダ名（未所属なら空文字）", "order": 0 }
  ```
  `order` は Python 側のお気に入りリストでの並び順（0始まり）。
- `thumbnails/<id>.png` — その `id` の画像。中央から正方形に切り出し、600px 角程度に縮小済み
  （アップスケールはしない）。元画像から作れないとき（動画、移動・削除済みのファイルなど）は、
  登録時に保存された 64×40 のサムネイルを切り出して拡大したものになるので、その場合は
  多少ぼやける
- リストにない `id` の `thumbnails/*.png` は、次にエクスポートされたときに削除されます

存在しないお気に入りの `id` を安全に無視すること（読み込み中に消える可能性があるため）。

## クリックで開く（widgetURL）

各画像には次の形式の URL を `widgetURL` として付けてください:

```
localmediaviewer://favorite?id=<favorites.jsonのid>
```

Python アプリ（`local_media_viewer.app.Application` / `MainWindow.handle_widget_url`）がこれを
受け取り、対応するお気に入りを開いて前面に出します。スキームやクエリの形を変える場合は
`src/local_media_viewer/mac_widget.py` の `URL_SCHEME` / `parse_widget_favorite_id` と、
`scripts/build_mac.sh` の Info.plist 登録（`CFBundleURLSchemes`）も合わせて変更すること。

## 決まっているレイアウト

| 種類 | サイズ | 配置 |
| --- | --- | --- |
| 1枚 | systemSmall | 1枚を大きく |
| 4枚 | systemSmall | 2×2 |
| 1＋4 | systemMedium | 左に大きい1枚、右に2×2の4枚 |
| 2＋8 | systemLarge | 上に大きい2枚、下に4×2の8枚 |
| 1枚 | systemLarge | 1枚を大きく |

## 選び方（Configuration App Intent）

お気に入りは Python 側の一覧（`favorites.json`、`order` 順）からそのまま表示する。
「ウィジェットを編集」で変えられるのは、どの枠にどのお気に入りを出すかの**入れ替えだけ**
（既定は `order` 順の先頭から詰めたもの）。フォルダ選択や1枚ごとの新規指定はしない。

## 署名について

無料の Apple ID（Personal Team）でひな形の表示は確認済み（2026-09-30時点）。ビルドは当面
ユーザーの Mac 上で Xcode（または `xcodebuild`）から行い、署名なしの GitHub Actions ビルドとは
別系統として扱う。
