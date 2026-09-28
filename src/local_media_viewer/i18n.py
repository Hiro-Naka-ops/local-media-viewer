"""User-facing text in every supported language.

The Japanese wording is the key, so the code still reads in the language the
UI was written in, and each entry lists what it becomes elsewhere. Kept free of
Qt, like settings.py, so the catalog can be checked without a display.
"""

from __future__ import annotations

JAPANESE = "ja"
ENGLISH = "en"
CHINESE = "zh"
KOREAN = "ko"

# An empty choice means "whatever Windows is set to".
AUTO = ""

# Names are written in their own language: someone who cannot read the
# current UI still has to be able to find theirs.
LANGUAGES: list[tuple[str, str]] = [
    (JAPANESE, "日本語"),
    (ENGLISH, "English"),
    (CHINESE, "简体中文"),
    (KOREAN, "한국어"),
]
CODES = {code for code, _name in LANGUAGES}

CATALOG: dict[str, dict[str, str]] = {
    # Toolbar
    "操作": {ENGLISH: "Controls", CHINESE: "操作", KOREAN: "조작"},
    "ファイルを開く": {ENGLISH: "Open File", CHINESE: "打开文件", KOREAN: "파일 열기"},
    "フォルダを開く": {ENGLISH: "Open Folder", CHINESE: "打开文件夹", KOREAN: "폴더 열기"},
    "前へ": {ENGLISH: "Previous", CHINESE: "上一个", KOREAN: "이전"},
    "次へ": {ENGLISH: "Next", CHINESE: "下一个", KOREAN: "다음"},
    "フィット／原寸": {
        ENGLISH: "Fit / Actual Size",
        CHINESE: "适应窗口／原始大小",
        KOREAN: "창에 맞춤／원본 크기",
    },
    "全画面表示": {ENGLISH: "Full Screen", CHINESE: "全屏显示", KOREAN: "전체 화면"},
    "フィルター": {ENGLISH: "Filters", CHINESE: "滤镜", KOREAN: "필터"},
    "フィルムストリップ": {ENGLISH: "Filmstrip", CHINESE: "胶片栏", KOREAN: "필름스트립"},
    "音量": {ENGLISH: "Volume", CHINESE: "音量", KOREAN: "음량"},
    "表示設定": {ENGLISH: "View Settings", CHINESE: "显示设置", KOREAN: "보기 설정"},
    "表示・並び順・見開き・言語の設定": {
        ENGLISH: "Display, sort order, spread and language settings",
        CHINESE: "显示、排序、双页和语言设置",
        KOREAN: "표시·정렬·두 페이지·언어 설정",
    },
    "お気に入り": {ENGLISH: "Favorites", CHINESE: "收藏夹", KOREAN: "즐겨찾기"},
    "登録したフォルダを開く": {
        ENGLISH: "Open a saved folder",
        CHINESE: "打开已收藏的文件夹",
        KOREAN: "저장한 폴더 열기",
    },
    # Video controls (shown only while a video is open)
    "▶ 再生": {ENGLISH: "▶ Play", CHINESE: "▶ 播放", KOREAN: "▶ 재생"},
    "❚❚ 一時停止": {ENGLISH: "❚❚ Pause", CHINESE: "❚❚ 暂停", KOREAN: "❚❚ 일시 정지"},
    "■ 停止": {ENGLISH: "■ Stop", CHINESE: "■ 停止", KOREAN: "■ 정지"},
    "再生／一時停止": {ENGLISH: "Play / Pause", CHINESE: "播放／暂停", KOREAN: "재생／일시 정지"},
    "動画をクリック": {ENGLISH: "click the video", CHINESE: "单击视频", KOREAN: "동영상 클릭"},
    "停止して先頭に戻す": {
        ENGLISH: "Stop and go back to the start",
        CHINESE: "停止并回到开头",
        KOREAN: "정지하고 처음으로 되돌리기",
    },
    "ミュート": {ENGLISH: "Mute", CHINESE: "静音", KOREAN: "음소거"},
    # Options
    "パン位置を毎回初期化する": {
        ENGLISH: "Reset Pan Position on Every Page",
        CHINESE: "每次翻页时重置平移位置",
        KOREAN: "페이지마다 이동 위치 초기화",
    },
    "見開き表示（2ページ）": {
        ENGLISH: "Two-Page Spread",
        CHINESE: "双页显示",
        KOREAN: "두 페이지 보기",
    },
    "見開きを右送りにする": {
        ENGLISH: "Right-to-Left Spread",
        CHINESE: "双页从右向左排列",
        KOREAN: "오른쪽에서 왼쪽으로 넘기기",
    },
    "1ページ目を表紙として単独表示": {
        ENGLISH: "Show First Page Alone as Cover",
        CHINESE: "首页作为封面单独显示",
        KOREAN: "첫 페이지를 표지로 단독 표시",
    },
    "見開きページをずらす": {
        ENGLISH: "Shift Spread by One Page",
        CHINESE: "双页错开一页",
        KOREAN: "두 페이지 한 장씩 밀기",
    },
    "組み合わせを1ページ分ずらす": {
        ENGLISH: "Shift the page pairing by one page",
        CHINESE: "将页面组合错开一页",
        KOREAN: "페이지 짝을 한 장 밀기",
    },
    "エフェクト": {ENGLISH: "Effect", CHINESE: "效果", KOREAN: "효과"},
    "線の色を選ぶ…": {
        ENGLISH: "Choose Line Color…",
        CHINESE: "选择线条颜色…",
        KOREAN: "선 색상 선택…",
    },
    "線の色": {ENGLISH: "Line Color", CHINESE: "线条颜色", KOREAN: "선 색상"},
    "並び順": {ENGLISH: "Sort Order", CHINESE: "排序", KOREAN: "정렬 순서"},
    "昇順": {ENGLISH: "Ascending", CHINESE: "升序", KOREAN: "오름차순"},
    "降順": {ENGLISH: "Descending", CHINESE: "降序", KOREAN: "내림차순"},
    "言語": {ENGLISH: "Language", CHINESE: "语言", KOREAN: "언어"},
    "システムに合わせる": {
        ENGLISH: "Follow System",
        CHINESE: "跟随系统",
        KOREAN: "시스템 설정 따르기",
    },
    # Effects (effects.EFFECT_LABELS)
    "なし": {ENGLISH: "None", CHINESE: "无", KOREAN: "없음"},
    "モノクロ": {ENGLISH: "Monochrome", CHINESE: "黑白", KOREAN: "흑백"},
    "セピア": {ENGLISH: "Sepia", CHINESE: "棕褐色", KOREAN: "세피아"},
    "線の色を変える": {
        ENGLISH: "Recolor Lines",
        CHINESE: "更改线条颜色",
        KOREAN: "선 색상 변경",
    },
    # Sort fields (media.SORT_LABELS)
    "ファイル・フォルダ名": {
        ENGLISH: "File / Folder Name",
        CHINESE: "文件／文件夹名称",
        KOREAN: "파일·폴더 이름",
    },
    "作成日時": {ENGLISH: "Date Created", CHINESE: "创建时间", KOREAN: "만든 날짜"},
    "更新日時": {ENGLISH: "Date Modified", CHINESE: "修改时间", KOREAN: "수정한 날짜"},
    # Filter panel
    "表示フィルター": {
        ENGLISH: "Display Filters",
        CHINESE: "显示滤镜",
        KOREAN: "표시 필터",
    },
    "元ファイルは変更されません": {
        ENGLISH: "Original files are never modified",
        CHINESE: "不会修改原始文件",
        KOREAN: "원본 파일은 변경되지 않습니다",
    },
    "明るさ": {ENGLISH: "Brightness", CHINESE: "亮度", KOREAN: "밝기"},
    "コントラスト": {ENGLISH: "Contrast", CHINESE: "对比度", KOREAN: "대비"},
    "ガンマ": {ENGLISH: "Gamma", CHINESE: "伽马", KOREAN: "감마"},
    "色相": {ENGLISH: "Hue", CHINESE: "色相", KOREAN: "색조"},
    "フィルターをリセット": {
        ENGLISH: "Reset Filters",
        CHINESE: "重置滤镜",
        KOREAN: "필터 초기화",
    },
    "動画には初期版では適用されません": {
        ENGLISH: "Filters are not applied to videos in this version",
        CHINESE: "此版本中滤镜不适用于视频",
        KOREAN: "이 버전에서는 동영상에 필터가 적용되지 않습니다",
    },
    "現在値: {value}（Ctrl+ドラッグで自由調整）": {
        ENGLISH: "Value: {value} (Ctrl+drag to adjust freely)",
        CHINESE: "当前值：{value}（按住 Ctrl 拖动可自由调整）",
        KOREAN: "현재 값: {value} (Ctrl+드래그로 자유 조정)",
    },
    # Opening files
    "画像・動画を開く": {
        ENGLISH: "Open Image or Video",
        CHINESE: "打开图片或视频",
        KOREAN: "이미지·동영상 열기",
    },
    "メディアファイル": {ENGLISH: "Media files", CHINESE: "媒体文件", KOREAN: "미디어 파일"},
    "非対応形式": {
        ENGLISH: "Unsupported Format",
        CHINESE: "不支持的格式",
        KOREAN: "지원하지 않는 형식",
    },
    "対応していないファイルです。\n{name}": {
        ENGLISH: "This file is not supported.\n{name}",
        CHINESE: "不支持此文件。\n{name}",
        KOREAN: "지원하지 않는 파일입니다.\n{name}",
    },
    "メディアなし": {ENGLISH: "No Media", CHINESE: "没有媒体", KOREAN: "미디어 없음"},
    "対応ファイルがありません。\n{folder}": {
        ENGLISH: "There are no supported files here.\n{folder}",
        CHINESE: "没有支持的文件。\n{folder}",
        KOREAN: "지원하는 파일이 없습니다.\n{folder}",
    },
    "画像を開けません": {
        ENGLISH: "Cannot Open Image",
        CHINESE: "无法打开图片",
        KOREAN: "이미지를 열 수 없습니다",
    },
    "次のフォルダへ移動": {
        ENGLISH: "Go to Next Folder",
        CHINESE: "转到下一个文件夹",
        KOREAN: "다음 폴더로 이동",
    },
    "前のフォルダへ移動": {
        ENGLISH: "Go to Previous Folder",
        CHINESE: "转到上一个文件夹",
        KOREAN: "이전 폴더로 이동",
    },
    "次のフォルダを開きますか？\n{name}": {
        ENGLISH: "Open the next folder?\n{name}",
        CHINESE: "要打开下一个文件夹吗？\n{name}",
        KOREAN: "다음 폴더를 열까요?\n{name}",
    },
    "前のフォルダを開きますか？\n{name}": {
        ENGLISH: "Open the previous folder?\n{name}",
        CHINESE: "要打开上一个文件夹吗？\n{name}",
        KOREAN: "이전 폴더를 열까요?\n{name}",
    },
    # Status bar
    "並び順: {field}（{way}）": {
        ENGLISH: "Sort order: {field} ({way})",
        CHINESE: "排序：{field}（{way}）",
        KOREAN: "정렬 순서: {field} ({way})",
    },
    "作成 {created}　更新 {modified}": {
        ENGLISH: "Created {created}   Modified {modified}",
        CHINESE: "创建 {created}　修改 {modified}",
        KOREAN: "생성 {created}   수정 {modified}",
    },
    "動画を再生できません: {error}": {
        ENGLISH: "Cannot play video: {error}",
        CHINESE: "无法播放视频：{error}",
        KOREAN: "동영상을 재생할 수 없습니다: {error}",
    },
    "一時停止": {ENGLISH: "Paused", CHINESE: "已暂停", KOREAN: "일시 정지"},
    "停止": {ENGLISH: "Stopped", CHINESE: "已停止", KOREAN: "정지"},
    "再生": {ENGLISH: "Playing", CHINESE: "播放", KOREAN: "재생"},
    # Favorites
    "お気に入りに登録": {
        ENGLISH: "Add to Favorites",
        CHINESE: "添加到收藏夹",
        KOREAN: "즐겨찾기에 추가",
    },
    "お気に入りに登録しました: {name}": {
        ENGLISH: "Added to favorites: {name}",
        CHINESE: "已添加到收藏夹：{name}",
        KOREAN: "즐겨찾기에 추가했습니다: {name}",
    },
    "お気に入りから解除": {
        ENGLISH: "Remove from Favorites",
        CHINESE: "从收藏夹移除",
        KOREAN: "즐겨찾기에서 삭제",
    },
    "お気に入りから解除しました: {name}": {
        ENGLISH: "Removed from favorites: {name}",
        CHINESE: "已从收藏夹移除：{name}",
        KOREAN: "즐겨찾기에서 삭제했습니다: {name}",
    },
    "お気に入りはありません": {
        ENGLISH: "No favorites yet",
        CHINESE: "暂无收藏",
        KOREAN: "즐겨찾기가 없습니다",
    },
    "右クリックで解除・フォルダ分け": {
        ENGLISH: "Right-click to remove or file into a folder",
        CHINESE: "右键单击可移除或归入文件夹",
        KOREAN: "오른쪽 클릭으로 삭제·폴더 분류",
    },
    "フォルダへ移動": {ENGLISH: "Move to Folder", CHINESE: "移至文件夹", KOREAN: "폴더로 이동"},
    "（フォルダなし）": {
        ENGLISH: "(No Folder)",
        CHINESE: "（无文件夹）",
        KOREAN: "(폴더 없음)",
    },
    "新しいフォルダ…": {ENGLISH: "New Folder…", CHINESE: "新建文件夹…", KOREAN: "새 폴더…"},
    "新しいフォルダ": {ENGLISH: "New Folder", CHINESE: "新建文件夹", KOREAN: "새 폴더"},
    "お気に入りをまとめるフォルダ名": {
        ENGLISH: "Name of the folder to group favorites in",
        CHINESE: "用于整理收藏的文件夹名称",
        KOREAN: "즐겨찾기를 묶을 폴더 이름",
    },
    "フォルダなし": {ENGLISH: "No Folder", CHINESE: "无文件夹", KOREAN: "폴더 없음"},
    "{name} を「{group}」へ移動しました": {
        ENGLISH: "Moved {name} to “{group}”",
        CHINESE: "已将 {name} 移至“{group}”",
        KOREAN: "{name}을(를) '{group}'(으)로 이동했습니다",
    },
    "フォルダが見つかりません": {
        ENGLISH: "Folder Not Found",
        CHINESE: "找不到文件夹",
        KOREAN: "폴더를 찾을 수 없습니다",
    },
    "お気に入りのフォルダが見つかりません。\n{path}": {
        ENGLISH: "The favorite folder could not be found.\n{path}",
        CHINESE: "找不到收藏的文件夹。\n{path}",
        KOREAN: "즐겨찾기 폴더를 찾을 수 없습니다.\n{path}",
    },
}

_current = JAPANESE


def resolve(choice: object, system: str) -> str:
    """The language to show: the one chosen, else Windows', else English.

    English is the fallback rather than Japanese because someone whose system
    language is not covered is more likely to read English.
    """
    for candidate in (choice, system):
        if isinstance(candidate, str) and candidate:
            base = candidate.replace("-", "_").split("_")[0].lower()
            if base in CODES:
                return base
    return ENGLISH


def set_language(code: str) -> None:
    global _current
    _current = code if code in CODES else ENGLISH


def current_language() -> str:
    return _current


def tr(text: str, **values: object) -> str:
    """Translate a Japanese UI string, filling any {placeholders} afterwards."""
    if _current != JAPANESE:
        text = CATALOG.get(text, {}).get(_current, text)
    return text.format(**values) if values else text


def language_menu_title() -> str:
    """The 言語 submenu title, always carrying the English word too.

    It is the one entry that has to be found by someone who cannot read the
    language the UI is currently in.
    """
    title = tr("言語")
    return title if _current == ENGLISH else f"{title} / Language"
