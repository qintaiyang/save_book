"""用量查询面板 — 显示今日用量 + 套餐信息"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QLineEdit, QMessageBox,
)
from PyQt6.QtCore import Qt
from ..components import PageHeader, StatCard, SurfaceCard, configure_page_layout


def _display_time(value):
    if not value:
        return "无"
    return str(value).replace("T", " ").split(".", 1)[0]


class UsagePanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self._stat_labels = {}  # label → QLabel reference
        self._init_ui()

    def _init_ui(self):
        layout = configure_page_layout(self)
        layout.addWidget(PageHeader(
            "用量查询", "查看卡密额度、到期时间与最近消费", "ACCOUNT USAGE"
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

        self.label_plan = QLabel("当前卡密: --")
        self.label_plan.setProperty("ui-role", "status")
        self.label_plan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.label_plan)

        self.label_card = QLabel("卡密状态: --")
        self.label_card.setProperty("ui-role", "status")
        self.label_card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.label_card)

        stats = QHBoxLayout()
        stats.setSpacing(16)

        for label, accent in [("已用", "accent"), ("剩余", "success"), ("总额", "neutral")]:
            box = StatCard(label, "--", accent)
            box.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stat_labels[label] = box.value
            stats.addWidget(box, 1)

        cl.addLayout(stats)

        card_row = QHBoxLayout()
        card_row.setSpacing(10)
        self.input_card_code = QLineEdit()
        self.input_card_code.setPlaceholderText("输入卡密")
        self.input_card_code.returnPressed.connect(self._bind_card)
        card_row.addWidget(self.input_card_code, 1)

        self.btn_bind = QPushButton("绑定卡密")
        self.btn_bind.setProperty("btn-type", "primary")
        self.btn_bind.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bind.clicked.connect(self._bind_card)
        card_row.addWidget(self.btn_bind)

        self.btn_unbind = QPushButton("取消绑定")
        self.btn_unbind.setProperty("btn-type", "secondary")
        self.btn_unbind.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_unbind.clicked.connect(self._unbind_card)
        card_row.addWidget(self.btn_unbind)
        cl.addLayout(card_row)

        self.btn_refresh = QPushButton("  刷新")
        self.btn_refresh.setProperty("btn-type", "secondary")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._refresh)
        cl.addWidget(self.btn_refresh)

        self.label_reset = QLabel("")
        self.label_reset.setProperty("ui-role", "status")
        self.label_reset.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.label_reset)

        self.label_ledger = QLabel("")
        self.label_ledger.setProperty("ui-role", "status")
        self.label_ledger.setWordWrap(True)
        self.label_ledger.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.label_ledger)

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
            if hasattr(self.client, "get_membership"):
                self._render_membership(self.client.get_membership())
            else:
                self._render_legacy_usage(self.client.get_usage())
        except Exception as e:
            for lbl in self._stat_labels.values():
                lbl.setText("?")
            self.label_plan.setText("当前卡密: ?")
            self.label_card.setText("卡密状态: ?")
            self.label_reset.setText(f"查询失败: {str(e)}")
            self.label_ledger.setText("")

    def _render_legacy_usage(self, usage):
        used = usage["chaptersUsed"]
        limit = usage["limit"]
        remaining = usage["remaining"]
        reset = usage.get("resetAt", "")

        self.label_plan.setText("当前卡密: 旧额度接口")
        self.label_card.setText("卡密状态: --")
        self._stat_labels["已用"].setText(str(used))
        self._stat_labels["剩余"].setText(str(remaining))
        self._stat_labels["总额"].setText(str(limit))
        self._set_progress(used, limit)
        self.label_reset.setText(f"重置时间: {reset}")
        self.label_ledger.setText("")

    def _render_membership(self, summary):
        subscription = summary.get("subscription") or {}
        card = summary.get("card") or {}
        quota = summary.get("quota") or {}
        ledger = summary.get("ledger") or []

        total = int(quota.get("total") or 0)
        used = int(quota.get("used") or 0)
        remaining = int(quota.get("remaining") or 0)
        plan_name = subscription.get("planName") or "无卡密"
        card_preview = card.get("preview") or "未绑定"
        card_status = card.get("status") or "none"
        expires_at = card.get("expiresAt") or subscription.get("periodEnd")

        self.label_plan.setText(f"当前卡密: {plan_name}")
        self.label_card.setText(f"卡密状态: {card_status} / {card_preview}")
        self._stat_labels["已用"].setText(str(used))
        self._stat_labels["剩余"].setText(str(remaining))
        self._stat_labels["总额"].setText(str(total))
        self._set_progress(used, total)
        self.label_reset.setText(f"到期时间: {_display_time(expires_at)}")
        self.btn_unbind.setEnabled(bool(card.get("id")))

        if ledger:
            recent = ledger[0]
            action = recent.get("action", "")
            amount = recent.get("amount", 0)
            balance = recent.get("balanceAfter", "")
            created = _display_time(recent.get("createdAt"))
            self.label_ledger.setText(f"最近消费: {action} {amount}，剩余额度 {balance}，时间 {created}")
        else:
            self.label_ledger.setText("最近消费: 无")

    def _set_progress(self, used, total):
        pct = min(100, int(used / total * 100)) if total > 0 else 0
        self.progress.setFormat(f"{used} / {total} 次 ({pct}%)")
        self.progress.setValue(pct)

    def _bind_card(self):
        code = self.input_card_code.text().strip()
        if not code:
            QMessageBox.warning(self, "提示", "请输入卡密")
            return
        try:
            self.client.bind_card(code)
            self.input_card_code.clear()
            self._refresh()
        except Exception as e:
            QMessageBox.critical(self, "绑定失败", str(e))

    def _unbind_card(self):
        try:
            self.client.unbind_card()
            self._refresh()
        except Exception as e:
            QMessageBox.critical(self, "取消绑定失败", str(e))
