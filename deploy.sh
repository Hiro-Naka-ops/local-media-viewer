#!/usr/bin/env bash
# =============================================================
# deploy.sh  —  テスト → コミット → GitHub へ push
# 使い方（Git Bash）:
#   ./deploy.sh                        # 変更内容からコミットメッセージを自動で作る
#   ./deploy.sh "フィルムストリップを修正"  # メッセージを引数で指定
#
# 自動のメッセージは表示して確認を求める。Enter でそのまま使い、
# 文字を入力するとその1行目と置き換える（変更ファイルの一覧は残る）。
#
# push してもビルドやリリースは始まらない。Windows 版・Mac 版を作るときは
# GitHub の Actions →「Build and release」→「Run workflow」を押す。
# =============================================================

set -euo pipefail
cd "$(dirname "$0")"

BRANCH="master"
REPO="Hiro-Naka-ops/local-media-viewer"

green()  { echo -e "\033[1;32m$*\033[0m"; }
yellow() { echo -e "\033[1;33m$*\033[0m"; }
red()    { echo -e "\033[1;31m$*\033[0m"; }

# ファイルの場所から、アプリのどの部分の変更かを「順位 TAB 名前」で返す。
# 順位は要約に並べる順（アプリ本体 → テスト → ビルド・ドキュメント）
area_of() {
    local name
    name="$(area_name "$1")"
    case "$1" in
        src/*)   printf '1\t%s\n' "$name" ;;
        tests/*) printf '2\t%s\n' "$name" ;;
        *)       printf '3\t%s\n' "$name" ;;
    esac
}

area_name() {
    case "$1" in
        src/local_media_viewer/app.py)        echo "メイン画面" ;;
        src/local_media_viewer/viewer.py)     echo "画像・動画の表示" ;;
        src/local_media_viewer/filmstrip.py)  echo "フィルムストリップ" ;;
        src/local_media_viewer/favorites.py)  echo "お気に入り" ;;
        src/local_media_viewer/spread.py)     echo "見開き" ;;
        src/local_media_viewer/filters.py)    echo "フィルター" ;;
        src/local_media_viewer/effects.py)    echo "エフェクト" ;;
        src/local_media_viewer/media.py)      echo "ファイル一覧・並び順" ;;
        src/local_media_viewer/sorticon.py)   echo "並び順アイコン" ;;
        src/local_media_viewer/preloader.py)  echo "先読み" ;;
        src/local_media_viewer/placement.py)  echo "ウィンドウ配置" ;;
        src/local_media_viewer/settings.py)   echo "設定の保存" ;;
        src/local_media_viewer/i18n.py)       echo "翻訳" ;;
        src/local_media_viewer/heic.py)       echo "HEIC対応" ;;
        src/local_media_viewer/appicon.py)    echo "アプリアイコン" ;;
        src/local_media_viewer/controls.py)   echo "スライダー" ;;
        src/*)                                echo "アプリ本体" ;;
        tests/*)                              echo "テスト" ;;
        .github/*|scripts/*|*.spec)           echo "ビルド設定" ;;
        deploy.sh)                            echo "deploy スクリプト" ;;
        assets/*)                             echo "画像素材" ;;
        pyproject.toml)                       echo "依存関係" ;;
        *.md)                                 echo "ドキュメント" ;;
        *)                                    echo "その他" ;;
    esac
}

# ステージ済みの変更から、要約1行＋ファイル一覧のコミットメッセージを作る
auto_message() {
    local status path newpath added removed summary area
    local -a areas

    # 要約: 変更のあった部分を順位順・重複なしで「・」でつなぐ。
    # 長くなりすぎないよう3つまでにして、残りは「ほか」にまとめる
    mapfile -t areas < <(
        git diff --cached --name-only | while read -r path; do
            area_of "$path"
        done | sort -s -t$'\t' -k1,1n | cut -f2 | awk '!seen[$0]++'
    )
    # IFS は複数バイトの「・」の先頭1バイトしか使わないので、手でつなぐ
    summary=""
    for area in "${areas[@]:0:3}"; do
        summary="${summary:+${summary}・}${area}"
    done
    [ "${#areas[@]}" -gt 3 ] && summary="${summary}ほか"
    echo "${summary}を更新"
    echo ""

    # 一覧: 追加・削除・名前変更と、変更行数
    while IFS=$'\t' read -r status path newpath; do
        case "$status" in
            A)  echo "- 追加: $path" ;;
            D)  echo "- 削除: $path" ;;
            R*) echo "- 名前変更: $path → $newpath" ;;
            *)
                read -r added removed _ < <(git diff --cached --numstat -- "$path")
                if [ "$added" = "-" ]; then
                    echo "- 変更: $path（バイナリ）"
                else
                    echo "- 変更: $path（+$added / -$removed）"
                fi
                ;;
        esac
    done < <(git diff --cached --name-status -M)
}

echo ""
echo "=============================="
green "[1/3] テスト"
echo "=============================="
# 実マウスカーソルの位置で成否が変わる既知の不安定テストは除く（.claude/CLAUDE.md 参照）
PYTHONPATH=src python -m pytest -q \
    --deselect tests/test_viewer_controls.py::test_video_timeline_overlay_shows_and_fades
python -m ruff check src tests

echo ""
echo "=============================="
green "[2/3] ローカルコミット"
echo "=============================="

# 新規ファイルも拾うため git status で判定する
if [ -z "$(git status --porcelain)" ]; then
    yellow "変更なし。コミットをスキップして push します。"
else
    git add -A
    git status --short
    echo ""

    if [ -n "${1:-}" ]; then
        MSG="$1"
    else
        MSG="$(auto_message)"
        yellow "コミットメッセージ（自動）:"
        echo "------------------------------"
        echo "$MSG"
        echo "------------------------------"
        yellow "Enter でこのまま使う。1行目を書き換えるときは入力してから Enter:"
        read -r SUBJECT
        if [ -n "$SUBJECT" ]; then
            # 1行目だけ差し替え、ファイル一覧は残す
            MSG="$SUBJECT"$'\n'"$(printf '%s\n' "$MSG" | tail -n +2)"
        fi
    fi
    git commit -q -F - <<< "$MSG"
    git log --oneline -1
fi

echo ""
echo "=============================="
green "[3/3] GitHub へ push"
echo "=============================="
if [ -z "$(git log --oneline "origin/$BRANCH..HEAD" 2>/dev/null)" ]; then
    yellow "push するコミットがありません。"
    exit 0
fi
git log --oneline "origin/$BRANCH..HEAD"
echo ""
git push origin "$BRANCH"

echo ""
green "================================"
green " push 完了！"
green " Windows 版・Mac 版を作るときは Actions →「Build and release」→「Run workflow」"
green " https://github.com/$REPO/actions"
green "================================"
