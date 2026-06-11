"""文本阅读器组件 — 分页/滚动 + 字体控制 + 暗色模式"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextOption
from ..components import SurfaceCard


class Reader(QWidget):
    """纯文本阅读器，支持字体大小调节和暗色切换"""

    def __init__(self):
        super().__init__()
        self._font_size = 16
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = SurfaceCard()
        toolbar.setProperty("ui-role", "reader-toolbar")
        toolbar.setFixedHeight(48)
        tr = QHBoxLayout(toolbar)
        tr.setContentsMargins(16, 4, 16, 4)
        tr.setSpacing(8)

        tr.addWidget(QLabel("字号:"))

        self.btn_font_smaller = QPushButton("A−")
        self.btn_font_smaller.setFixedSize(32, 28)
        self.btn_font_smaller.setProperty("btn-type", "secondary")
        self.btn_font_smaller.clicked.connect(lambda: self._adjust_font(-2))
        tr.addWidget(self.btn_font_smaller)

        self.btn_font_larger = QPushButton("A+")
        self.btn_font_larger.setFixedSize(32, 28)
        self.btn_font_larger.setProperty("btn-type", "secondary")
        self.btn_font_larger.clicked.connect(lambda: self._adjust_font(2))
        tr.addWidget(self.btn_font_larger)

        tr.addSpacing(20)

        tr.addStretch()

        self.label_info = QLabel("")
        self.label_info.setProperty("ui-role", "status")
        tr.addWidget(self.label_info)

        layout.addWidget(toolbar)

        # Text area
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setProperty("ui-role", "reader-content")
        self.text_edit.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.text_edit.setFont(QFont("Microsoft YaHei", self._font_size))
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.text_edit, 1)

    def load_text(self, text: str, title: str = ""):
        self.text_edit.setPlainText(text)
        char_count = len(text)
        cjk = sum(1 for c in text if '一' <= c <= '鿿')
        self.label_info.setText(f"{char_count} 字符 | {cjk} 中文字 | 字号 {self._font_size}")

    def _adjust_font(self, delta: int):
        self._font_size = max(10, min(36, self._font_size + delta))
        self.text_edit.setFont(QFont("Microsoft YaHei", self._font_size))

    def clear(self):
        self.text_edit.clear()
        self.label_info.setText("")
