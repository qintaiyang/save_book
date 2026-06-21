import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from PyQt6.QtWidgets import QApplication, QLabel

from qidian_save.desktop.panels.usage_panel import UsagePanel

_QT_APP = None


class FakeMembershipClient:
    def __init__(self):
        self.bound_codes = []
        self.unbound = 0
        self.summary = {
            "subscription": {
                "status": "active",
                "planName": "开发测试卡",
                "periodEnd": "2026-07-01T12:00:00",
            },
            "card": {
                "id": 7,
                "status": "bound",
                "preview": "CARD****0001",
                "expiresAt": "2026-07-01T12:00:00",
            },
            "quota": {"total": 100, "used": 35, "remaining": 65},
            "ledger": [
                {"action": "consume", "amount": 3, "balanceAfter": 65, "createdAt": "2026-06-21T08:00:00"},
            ],
        }

    def get_membership(self):
        return self.summary

    def bind_card(self, code):
        self.bound_codes.append(code)
        self.summary["card"]["preview"] = "NEW****CARD"
        self.summary["quota"] = {"total": 200, "used": 0, "remaining": 200}
        return {"ok": True}

    def unbind_card(self):
        self.unbound += 1
        self.summary["card"] = {"id": None, "status": "none", "preview": "", "expiresAt": None}
        self.summary["subscription"] = {"status": "none", "planName": "无卡密", "periodEnd": None}
        self.summary["quota"] = {"total": 0, "used": 0, "remaining": 0}
        return {"ok": True}


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _all_text(panel):
    return "\n".join(child.text() for child in panel.findChildren(QLabel))


def test_usage_panel_renders_membership_summary():
    _app()
    panel = UsagePanel(FakeMembershipClient())

    text = _all_text(panel)
    assert "开发测试卡" in text
    assert "CARD****0001" in text
    assert "65" in text
    assert panel.progress.value() == 35


def test_usage_panel_binds_and_unbinds_card():
    _app()
    client = FakeMembershipClient()
    panel = UsagePanel(client)

    panel.input_card_code.setText(" CARD-NEW ")
    panel._bind_card()
    assert client.bound_codes == ["CARD-NEW"]
    assert "NEW****CARD" in _all_text(panel)

    panel._unbind_card()
    assert client.unbound == 1
    assert "无卡密" in _all_text(panel)
