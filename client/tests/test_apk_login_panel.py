import os
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.apk_login_panel import ApkLoginPanel


class FakeClient:
    base_url = "http://127.0.0.1:8765"

    def __init__(self):
        self.last_challenge_payload = None
        self.last_create_session_args = None

    def create_apk_login_session(self, account, password, client_meta=None):
        self.last_create_session_args = (account, password, client_meta)
        if (client_meta or {}).get("loginMode") == "phone_code":
            return {"sessionId": 2, "stage": "need_sms", "challenge": {"kind": "sms", "title": "SMS verification"}}
        return {"sessionId": 1, "stage": "need_captcha", "challenge": {"kind": "captcha", "title": "Human verification"}}

    def submit_apk_login_challenge(self, session_id, payload):
        self.last_challenge_payload = payload
        return {"sessionId": session_id, "stage": "authenticated", "challenge": None}


class ApkLoginPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_title_says_login(self):
        panel = ApkLoginPanel(FakeClient())
        from PyQt6.QtWidgets import QLabel
        labels = [child.text() for child in panel.findChildren(QLabel)]
        joined = "\n".join(labels)
        self.assertIn("登录", joined)

    def test_password_mode_by_default(self):
        panel = ApkLoginPanel(FakeClient())
        self.assertEqual(panel._login_mode, "password")
        self.assertFalse(panel.password_input.isHidden())
        self.assertTrue(panel.sms_code_input.isHidden())

    def test_phone_mode_shows_sms_input(self):
        panel = ApkLoginPanel(FakeClient())
        panel._set_login_mode("phone_code")
        self.assertFalse(panel.sms_code_input.isHidden())
        self.assertFalse(panel.sms_code_input.isEnabled())
        self.assertTrue(panel.password_input.isHidden())

    def test_create_session_sends_account_password(self):
        client = FakeClient()
        panel = ApkLoginPanel(client)
        panel._run = lambda func, ok_signal: ok_signal.emit(func())
        panel.account_input.setText("test@example.com")
        panel.password_input.setText("mypassword")
        panel._create_session()
        self.assertEqual(client.last_create_session_args[0], "test@example.com")
        self.assertEqual(client.last_create_session_args[1], "mypassword")

    def test_create_session_sends_phone_code_meta(self):
        client = FakeClient()
        panel = ApkLoginPanel(client)
        panel._run = lambda func, ok_signal: ok_signal.emit(func())
        panel._set_login_mode("phone_code")
        panel.account_input.setText("13800138000")
        panel._create_session()
        self.assertEqual(client.last_create_session_args[2]["loginMode"], "phone_code")

    def test_authenticated_session_invokes_callback(self):
        seen = []
        panel = ApkLoginPanel(FakeClient(), on_session_authenticated=lambda session_id: seen.append(session_id))
        panel._on_session_ready({"sessionId": 9, "stage": "authenticated"})
        self.assertEqual(seen, [9])
        self.assertIn("登录成功", panel.login_status.text())

    def test_need_captcha_shows_captcha_prompt(self):
        panel = ApkLoginPanel(FakeClient())
        with patch.object(panel, "_open_captcha"):
            panel._on_session_ready({
                "sessionId": 1,
                "stage": "need_captcha",
                "challenge": {"kind": "captcha", "data": {"captchaAppId": "test"}},
            })
        self.assertIn("需要完成滑块验证", panel.login_status.text())
        self.assertIn("自动打开滑块", panel.challenge_hint.text())

    def test_need_sms_shows_sms_prompt(self):
        panel = ApkLoginPanel(FakeClient())
        with patch.object(panel, "_open_captcha"):
            panel._on_session_ready({
                "sessionId": 2,
                "stage": "need_sms",
                "challenge": {"kind": "sms", "data": {"sessionKey": "phone-key-1"}},
            })
        self.assertIn("短信验证码已发送", panel.login_status.text())
        self.assertFalse(panel.sms_code_input.isHidden())
        self.assertFalse(panel.btn_submit_sms.isHidden())

    def test_submit_sms_sends_phone_code(self):
        client = FakeClient()
        panel = ApkLoginPanel(client)
        panel._run = lambda func, ok_signal: ok_signal.emit(func())
        panel._on_session_ready({
            "sessionId": 2,
            "stage": "need_sms",
            "challenge": {"kind": "sms"},
        })
        panel.sms_code_input.setText("123456")
        panel._submit_sms_code()
        self.assertEqual(client.last_challenge_payload, {"kind": "sms", "phoneCode": "123456"})

    def test_failed_challenge_shows_error(self):
        panel = ApkLoginPanel(FakeClient())
        panel._on_session_ready({
            "sessionId": 1,
            "stage": "need_captcha",
            "challengeResult": {"ok": False, "message": "验证码失败"},
        })
        self.assertIn("验证码失败", panel.login_status.text())
        self.assertIn("登录未完成", panel.login_status.text())

    def test_captcha_callback_submits_ticket(self):
        client = FakeClient()
        panel = ApkLoginPanel(client)
        panel.session_id = 1
        panel._run = lambda func, ok_signal: ok_signal.emit(func())
        panel._handle_captcha_callback({"ticket": "t", "randstr": "r", "state": panel._captcha_state})
        self.assertIsNotNone(client.last_challenge_payload)
        payload = client.last_challenge_payload
        self.assertEqual(payload.get("answer", {}).get("ticket"), "t")
        self.assertEqual(payload.get("answer", {}).get("randstr"), "r")

    def test_panel_has_no_debug_only_controls_in_normal_mode(self):
        panel = ApkLoginPanel(FakeClient())
        self.assertTrue(panel.debug_view.isHidden())

    def test_debug_view_visible_in_debug_mode(self):
        panel = ApkLoginPanel(FakeClient(), debug_mode=True)
        self.assertFalse(panel.debug_view.isHidden())

    def test_sms_submit_disabled_without_session(self):
        panel = ApkLoginPanel(FakeClient())
        panel.sms_code_input.setText("123456")
        with patch("qidian_save.desktop.panels.apk_login_panel.QMessageBox.warning") as warn:
            panel._submit_sms_code()
            warn.assert_called_once()

    def test_need_sms_enables_sms_submit(self):
        panel = ApkLoginPanel(FakeClient())
        panel._on_session_ready({
            "sessionId": 2,
            "stage": "need_sms",
            "challenge": {"kind": "sms"},
        })
        self.assertFalse(panel.btn_submit_sms.isEnabled())
        panel.sms_code_input.setText("654321")
        self.assertTrue(panel.btn_submit_sms.isEnabled())

    def test_set_login_mode_updates_button_text(self):
        panel = ApkLoginPanel(FakeClient())
        self.assertIn("检测账号", panel.btn_create_session.text())
        panel._set_login_mode("phone_code")
        self.assertIn("发送短信验证码", panel.btn_create_session.text())


if __name__ == "__main__":
    unittest.main()
