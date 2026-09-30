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
    "ツールバー": {ENGLISH: "Toolbar", CHINESE: "工具栏", KOREAN: "도구 모음"},
    "ステータスバー": {ENGLISH: "Status Bar", CHINESE: "状态栏", KOREAN: "상태 표시줄"},
    "音量": {ENGLISH: "Volume", CHINESE: "音量", KOREAN: "음량"},
    # Menu bar. The (&X) letter is the Alt key, written the way Windows
    # writes it for languages whose words have no Latin letter to underline.
    "ファイル(&F)": {ENGLISH: "&File", CHINESE: "文件(&F)", KOREAN: "파일(&F)"},
    "表示(&V)": {ENGLISH: "&View", CHINESE: "视图(&V)", KOREAN: "보기(&V)"},
    "見開き(&S)": {ENGLISH: "&Spread", CHINESE: "双页(&S)", KOREAN: "두 페이지(&S)"},
    "お気に入り(&A)": {ENGLISH: "F&avorites", CHINESE: "收藏夹(&A)", KOREAN: "즐겨찾기(&A)"},
    "ファイルを開く…": {ENGLISH: "Open File…", CHINESE: "打开文件…", KOREAN: "파일 열기…"},
    "フォルダを開く…": {ENGLISH: "Open Folder…", CHINESE: "打开文件夹…", KOREAN: "폴더 열기…"},
    "ウィンドウ(&W)": {ENGLISH: "&Window", CHINESE: "窗口(&W)", KOREAN: "창(&W)"},
    "常に手前に表示": {ENGLISH: "Always on Top", CHINESE: "窗口置顶", KOREAN: "항상 위에 표시"},
    "最大化": {ENGLISH: "Maximize", CHINESE: "最大化", KOREAN: "최대화"},
    "画面の左半分に配置": {
        ENGLISH: "Left Half of Screen",
        CHINESE: "放到屏幕左半边",
        KOREAN: "화면 왼쪽 절반에 배치",
    },
    "画面の右半分に配置": {
        ENGLISH: "Right Half of Screen",
        CHINESE: "放到屏幕右半边",
        KOREAN: "화면 오른쪽 절반에 배치",
    },
    "画面の中央に移動": {
        ENGLISH: "Center on Screen",
        CHINESE: "移到屏幕中央",
        KOREAN: "화면 가운데로 이동",
    },
    "次のディスプレイへ移動": {
        ENGLISH: "Move to Next Display",
        CHINESE: "移到下一个显示器",
        KOREAN: "다음 디스플레이로 이동",
    },
    "表示サイズ": {ENGLISH: "Display Size", CHINESE: "显示大小", KOREAN: "표시 크기"},
    "ウィンドウに合わせる": {
        ENGLISH: "Fit to Window",
        CHINESE: "适应窗口",
        KOREAN: "창에 맞춤",
    },
    "横幅に合わせる": {ENGLISH: "Fit to Width", CHINESE: "适应宽度", KOREAN: "너비에 맞춤"},
    "縦幅に合わせる": {ENGLISH: "Fit to Height", CHINESE: "适应高度", KOREAN: "높이에 맞춤"},
    "原寸で表示": {ENGLISH: "Actual Size", CHINESE: "原始大小", KOREAN: "원본 크기"},
    "幅を固定": {ENGLISH: "Fixed Width", CHINESE: "固定宽度", KOREAN: "고정 너비"},
    "幅100%で固定": {
        ENGLISH: "Fixed at 100% Width",
        CHINESE: "固定为100%宽度",
        KOREAN: "너비 100%로 고정",
    },
    "幅80%で固定": {
        ENGLISH: "Fixed at 80% Width",
        CHINESE: "固定为80%宽度",
        KOREAN: "너비 80%로 고정",
    },
    "幅60%で固定": {
        ENGLISH: "Fixed at 60% Width",
        CHINESE: "固定为60%宽度",
        KOREAN: "너비 60%로 고정",
    },
    "幅40%で固定": {
        ENGLISH: "Fixed at 40% Width",
        CHINESE: "固定为40%宽度",
        KOREAN: "너비 40%로 고정",
    },
    "幅20%で固定": {
        ENGLISH: "Fixed at 20% Width",
        CHINESE: "固定为20%宽度",
        KOREAN: "너비 20%로 고정",
    },
    "移動(&G)": {ENGLISH: "&Go", CHINESE: "转到(&G)", KOREAN: "이동(&G)"},
    "最初のページ": {ENGLISH: "First Page", CHINESE: "第一页", KOREAN: "첫 페이지"},
    "最後のページ": {ENGLISH: "Last Page", CHINESE: "最后一页", KOREAN: "마지막 페이지"},
    "ページを指定…": {ENGLISH: "Go to Page…", CHINESE: "转到页…", KOREAN: "페이지 이동…"},
    "ページを指定": {ENGLISH: "Go to Page", CHINESE: "转到页", KOREAN: "페이지 이동"},
    "ページ番号（1〜{count}）:": {
        ENGLISH: "Page number (1–{count}):",
        CHINESE: "页码（1–{count}）:",
        KOREAN: "페이지 번호（1–{count}）:",
    },
    "パン位置": {ENGLISH: "Pan Position", CHINESE: "平移位置", KOREAN: "이동 위치"},
    "毎回先頭に戻す": {
        ENGLISH: "Start at the Top Every Time",
        CHINESE: "每次回到顶部",
        KOREAN: "매번 맨 위에서 시작",
    },
    "前のページの位置を引き継ぐ": {
        ENGLISH: "Keep the Previous Page's Position",
        CHINESE: "沿用上一页的位置",
        KOREAN: "이전 페이지 위치 유지",
    },
    "固定した位置に合わせる": {
        ENGLISH: "Go to the Fixed Position",
        CHINESE: "移到固定的位置",
        KOREAN: "고정한 위치로 이동",
    },
    "今の位置で固定する": {
        ENGLISH: "Fix the Current Position",
        CHINESE: "固定当前位置",
        KOREAN: "현재 위치로 고정",
    },
    "この位置でパン位置を固定しました": {
        ENGLISH: "Pan position fixed here",
        CHINESE: "已将平移位置固定在此处",
        KOREAN: "이 위치로 고정했습니다",
    },
    "終了(&X)": {ENGLISH: "E&xit", CHINESE: "退出(&X)", KOREAN: "끝내기(&X)"},
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
    "クリックで並び順を変更": {
        ENGLISH: "Click to change the sort order",
        CHINESE: "单击以更改排序",
        KOREAN: "클릭하여 정렬 순서 변경",
    },
    "作成 {created}　更新 {modified}": {
        ENGLISH: "Created {created}   Modified {modified}",
        CHINESE: "创建 {created}　修改 {modified}",
        KOREAN: "생성 {created}   수정 {modified}",
    },
    "高画質化": {ENGLISH: "Enhance", CHINESE: "画质增强", KOREAN: "화질 개선"},
    "この画像のブロックノイズを消して解像度を上げる（表示のみ・元ファイルは変更しない）": {
        ENGLISH: "Remove block noise from this picture and raise its resolution"
        " (display only; the file is not changed)",
        CHINESE: "去除此图像的块状噪点并提高分辨率（仅用于显示，不修改原文件）",
        KOREAN: "이 이미지의 블록 노이즈를 없애고 해상도를 높입니다(표시 전용, 원본 파일은 변경하지 않음)",
    },
    "高画質化しています…": {
        ENGLISH: "Enhancing…",
        CHINESE: "正在增强画质…",
        KOREAN: "화질을 개선하는 중…",
    },
    "高画質化しました（{width}×{height}）": {
        ENGLISH: "Enhanced ({width}×{height})",
        CHINESE: "已增强画质（{width}×{height}）",
        KOREAN: "화질을 개선했습니다({width}×{height})",
    },
    "高画質化できませんでした": {
        ENGLISH: "Could not enhance this picture",
        CHINESE: "无法增强此图像的画质",
        KOREAN: "화질을 개선할 수 없습니다",
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
