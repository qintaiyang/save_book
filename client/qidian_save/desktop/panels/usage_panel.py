"""用量查询面板 — 显示今日用量 + 套餐信息"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar,
)
from PyQt6.QtCore import Qt
from ..components import PageHeader, StatCard, SurfaceCard, configure_page_layout


class UsagePanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self._stat_labels = {}  # label → QLabel reference
        self._init_ui()

    def _init_ui(self):
        layout = configure_page_layout(self)
        layout.addWidget(PageHeader(
            "用量查询", "查看今日章节额度与下次重置时间", "ACCOUNT USAGE"
        ))

        card = SurfaceCard()
        card.setMaximumWidth(760)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 22, 24, 22)
        cl.setSpacing(20)

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(24)
        cl.addWidget(self.progress)

        # Stat cards
        stats = QHBoxLayout()
        stats.setSpacing(16)

        for label, accent in [("已用", "accent"), ("剩余", "success"), ("限额", "neutral")]:
            box = StatCard(label, "--", accent)
            box.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stat_labels[label] = box.value
            stats.addWidget(box, 1)

        cl.addLayout(stats)

        # Refresh button
        self.btn_refresh = QPushButton("  刷新")
        self.btn_refresh.setProperty("btn-type", "secondary")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._refresh)
        cl.addWidget(self.btn_refresh)

        # Reset time
        self.label_reset = QLabel("")
        self.label_reset.setProperty("ui-role", "status")
        self.label_reset.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.label_reset)

        centered = QHBoxLayout()
        centered.addStretch()
        centered.addWidget(card, 1)
        centered.addStretch()
        layout.addLayout(centered)
        layout.addStretch()

        # Auto refresh on init
        self._refresh()

    def _refresh(self):
        try:
            usage = self.client.get_usage()
            used = usage["chaptersUsed"]
            limit = usage["limit"]
            remaining = usage["remaining"]
            reset = usage.get("resetAt", "")

            self._stat_labels["已用"].setText(str(used))
            self._stat_labels["剩余"].setText(str(remaining))
            self._stat_labels["限额"].setText(str(limit))

            pct = min(100, int(used / limit * 100)) if limit > 0 else 0
            self.progress.setFormat(f"{used} / {limit} 次 ({pct}%)")
            self.progress.setValue(pct)

            self.label_reset.setText(f"重置时间: {reset}")
        except Exception as e:
            for lbl in self._stat_labels.values():
                lbl.setText("?")
            self.label_reset.setText(f"查询失败: {str(e)}")
