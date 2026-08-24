from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QToolButton, QWidget

from local_media_viewer.media import VIDEO_EXTENSIONS


class Filmstrip(QWidget):
    selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.files: list[Path] = []
        self.buttons: list[QToolButton] = []
        self.setFixedHeight(112)
        self.setStyleSheet("background: #1D1D1D;")

        self.content = QWidget()
        self.row = QHBoxLayout(self.content)
        self.row.setContentsMargins(8, 6, 8, 6)
        self.row.setSpacing(6)
        self.row.addStretch()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidget(self.content)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

    def set_files(self, files: list[Path]) -> None:
        if files == self.files:
            return
        self.files = list(files)
        for button in self.buttons:
            self.row.removeWidget(button)
            button.deleteLater()
        self.buttons.clear()

        for index, path in enumerate(files):
            button = self._make_button(path, index)
            self.row.insertWidget(self.row.count() - 1, button)
            self.buttons.append(button)

    def set_current(self, index: int) -> None:
        for button_index, button in enumerate(self.buttons):
            selected = button_index == index
            border = "3px solid #F79009" if selected else "1px solid #555555"
            button.setStyleSheet(
                f"QToolButton {{ color: white; background: #292929; border: {border}; }}"
                "QToolButton:hover { background: #3A3A3A; }"
            )
        if 0 <= index < len(self.buttons):
            self.scroll.ensureWidgetVisible(self.buttons[index], 30, 0)

    def _make_button(self, path: Path, index: int) -> QToolButton:
        button = QToolButton()
        button.setFixedSize(104, 88)
        button.setToolTip(str(path))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(88, 62))
        label = path.name if len(path.name) <= 14 else f"{path.name[:11]}…"
        button.setText(f"▶ {label}" if path.suffix.lower() in VIDEO_EXTENSIONS else label)
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                size.scale(QSize(88, 62), Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(size)
            image = reader.read()
            if not image.isNull():
                button.setIcon(QIcon(QPixmap.fromImage(image)))
        button.clicked.connect(lambda _checked=False, item=index: self.selected.emit(item))
        return button
