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

from qidian_save.desktop.panels.apk_backup_panel import ApkBackupPanel


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
        return {"sessionId": session_id, "stage": "authenticated", "challenge": None, "taskId": 7, "task": {"taskId": 7, "status": "queued", "progressDone": 0, "progressTotal": 3}}

    def create_apk_backup_task(self, session_id, target_ref=None):
        return {"taskId": 7}

    def get_apk_task(self, task_id):
        return {"taskId": task_id, "status": "completed", "progressDone": 1, "progressTotal": 1}

    def list_apk_task_artifacts(self, task_id):
        return [{"artifactId": 11, "filename": "apk_backup_7.json", "artifactType": "apk", "sizeBytes": 10}]


class ApkBackupPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_constructs_with_apk_roles(self):
        panel = ApkBackupPanel(FakeClient())
        self.assertEqual(panel.property("ui-role"), None)
        self.assertEqual(panel.btn_create_session.property("btn-type"), "primary")
        self.assertEqual(panel.btn_toggle_debug.property("btn-type"), "secondary")
        self.assertFalse(hasattr(panel, "btn_open_captcha"))
        self.assertFalse(hasattr(panel, "btn_submit_challenge"))

    def test_panel_accepts_json_challenge_payload(self):
        panel = ApkBackupPanel(FakeClient())
        panel.challenge_input.setText('{"sessionKey":"s","ticket":"t","randstr":"r"}')
        payload = panel._challenge_payload()
        self.assertEqual(payload["kind"], "captcha")
        self.assertEqual(payload["answer"]["ticket"], "t")
        self.assertEqual(payload["answer"]["randstr"], "r")


    def test_submit_challenge_payload_can_include_target_and_start_task(self):
        client = FakeClient()
        panel = ApkBackupPanel(client)
        panel.session_id = 1
        panel.challenge_input.setText('{"ticket":"t","randstr":"r"}')
        panel.target_input.setText('{"bookId":100,"chapterId":123}')
        payload = panel._challenge_payload(start_task=True)
        self.assertTrue(payload["startTask"])
        self.assertEqual(payload["targetRef"]["bookId"], 100)
        self.assertEqual(payload["answer"]["ticket"], "t")

    def test_session_response_with_task_updates_task_id(self):
        panel = ApkBackupPanel(FakeClient())
        panel._on_session_ready({"sessionId": 1, "stage": "authenticated", "taskId": 7, "task": {"taskId": 7, "status": "queued", "progressDone": 0, "progressTotal": 3}})
        self.assertEqual(panel.task_id, 7)
        self.assertIn("任务 #7", panel.task_status.text())


    def test_captcha_url_uses_server_probe_page(self):
        panel = ApkBackupPanel(FakeClient())
        self.assertTrue(panel._captcha_url().startswith("http://127.0.0.1:8765/api/v1/apk/captcha/tencent"))
        self.assertIn("state=", panel._captcha_url())


    def test_captcha_url_can_include_local_callback(self):
        panel = ApkBackupPanel(FakeClient())
        panel._captcha_callback_url = "http://127.0.0.1:32123/captcha"
        panel._captcha_state = "state-1"
        url = panel._captcha_url()
        self.assertIn("callback=http%3A%2F%2F127.0.0.1%3A32123%2Fcaptcha", url)
        self.assertIn("state=state-1", url)


    def test_panel_title_mentions_fast_backup(self):
        panel = ApkBackupPanel(FakeClient())
        labels = [child.text() for child in panel.findChildren(__import__("PyQt6.QtWidgets").QtWidgets.QLabel)]
        joined = "\n".join(labels)
        self.assertIn("快速备份", joined)


    def test_session_ready_shows_verified_login_result(self):
        panel = ApkBackupPanel(FakeClient())
        panel._on_session_ready({"sessionId": 1, "stage": "authenticated", "challengeResult": {"ok": True}})
        self.assertIn("账号登录已确认", panel.login_status.text())


    def test_backup_actions_disabled_until_login_verified(self):
        panel = ApkBackupPanel(FakeClient())
        self.assertFalse(panel.btn_create_task.isEnabled())
        self.assertFalse(panel.btn_submit_sms.isEnabled())
        panel._on_session_ready({"sessionId": 1, "stage": "need_captcha", "challenge": {"kind": "captcha"}})
        self.assertFalse(panel.btn_create_task.isEnabled())
        self.assertFalse(panel.btn_submit_sms.isVisible())
        panel._on_session_ready({"sessionId": 1, "stage": "authenticated", "challengeResult": {"ok": True}})
        self.assertTrue(panel.btn_create_task.isEnabled())
        self.assertFalse(panel.btn_submit_sms.isEnabled())

    def test_failed_challenge_result_keeps_backup_disabled(self):
        panel = ApkBackupPanel(FakeClient())
        panel._on_session_ready({"sessionId": 1, "stage": "need_captcha", "challengeResult": {"ok": False, "message": "验证码失败"}})
        self.assertFalse(panel.btn_create_task.isEnabled())
        self.assertIn("账号登录未完成", panel.login_status.text())

    def test_captcha_state_shows_beginner_prompt_not_raw_json(self):
        panel = ApkBackupPanel(FakeClient())
        panel._on_session_ready({
            "sessionId": 1,
            "stage": "need_captcha",
            "challenge": {
                "kind": "captcha",
                "data": {
                    "provider": "tencent",
                    "captchaAppId": "1600000770",
                    "sessionKey": "secret-session-key",
                },
            },
        })
        self.assertIn("需要完成滑块验证", panel.login_status.text())
        self.assertIn("自动打开滑块", panel.challenge_hint.text())
        self.assertNotIn("secret-session-key", panel.challenge_hint.text())
        self.assertFalse(panel.debug_view.isVisible())

    def test_target_ref_uses_advanced_json_only(self):
        panel = ApkBackupPanel(FakeClient())
        panel.target_input.setText('{"bookId":100,"chapterIds":[123],"timeout":45}')
        target = panel._target_ref()
        self.assertEqual(target, {"bookId": 100, "chapterIds": [123], "timeout": 45})

    def test_invalid_advanced_target_ref_reports_json_message(self):
        panel = ApkBackupPanel(FakeClient())
        panel.target_input.setText("{bad json")
        with self.assertRaisesRegex(ValueError, "高级目标必须是 JSON"):
            panel._target_ref()

    def test_failed_challenge_result_shows_simple_retry_message(self):
        panel = ApkBackupPanel(FakeClient())
        panel._on_session_ready({
            "sessionId": 1,
            "stage": "need_captcha",
            "challengeResult": {"ok": False, "message": "验证码失败"},
        })
        self.assertIn("验证码失败", panel.login_status.text())
        self.assertIn("重新点击“检测账号”", panel.challenge_hint.text())
        self.assertNotIn("{", panel.login_status.text())

    def test_auto_captcha_callback_submits_ticket_and_randstr(self):
        client = FakeClient()
        panel = ApkBackupPanel(client)
        panel.session_id = 1
        panel._handle_captcha_callback({"ticket": "t", "randstr": "r", "state": panel._captcha_state})
        payload = panel._challenge_payload()
        self.assertEqual(payload["answer"]["ticket"], "t")
        self.assertEqual(payload["answer"]["randstr"], "r")

    def test_captcha_callback_closes_popup_window(self):
        class FakeDialog:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

            def deleteLater(self):
                pass

        panel = ApkBackupPanel(FakeClient())
        panel.session_id = 1
        dialog = FakeDialog()
        panel._captcha_dialog = dialog
        panel._handle_captcha_callback({"ticket": "t", "randstr": "r", "state": panel._captcha_state})
        self.assertTrue(dialog.closed)
        self.assertIsNone(panel._captcha_dialog)

    def test_apk_panel_hides_manual_captcha_controls_from_beginner_flow(self):
        panel = ApkBackupPanel(FakeClient())
        self.assertFalse(panel.challenge_input.isVisible())
        self.assertFalse(panel.btn_submit_sms.isVisible())

    def test_open_captcha_prefers_popup_window_over_inline_card(self):
        panel = ApkBackupPanel(FakeClient())
        opened = []
        panel._show_captcha_popup = lambda url: opened.append(url)
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
            with patch("qidian_save.desktop.panels.apk_backup_panel.QWebEngineView", object):
                with patch("qidian_save.desktop.panels.apk_backup_panel.QWebChannel", object):
                    panel._open_captcha()
        self.assertEqual(len(opened), 1)
        self.assertFalse(panel.captcha_card.isVisible())

    def test_phone_login_mode_sends_phone_code_client_meta(self):
        client = FakeClient()
        panel = ApkBackupPanel(client)
        panel._run = lambda func, ok_signal: ok_signal.emit(func())
        panel.btn_mode_phone.setChecked(True)
        panel._set_login_mode("phone_code")
        panel.account_input.setText("13800138000")
        panel._create_session()
        self.assertEqual(client.last_create_session_args[2]["loginMode"], "phone_code")

    def test_need_sms_stage_shows_simple_sms_prompt(self):
        panel = ApkBackupPanel(FakeClient())
        panel._on_session_ready({
            "sessionId": 2,
            "stage": "need_sms",
            "challenge": {"kind": "sms", "data": {"sessionKey": "phone-key-1"}},
        })
        self.assertIn("短信验证码", panel.login_status.text())
        self.assertFalse(panel.sms_code_input.isHidden())
        self.assertFalse(panel.btn_submit_sms.isHidden())
        self.assertIn("提交短信验证码", panel.btn_submit_sms.text())

    def test_phone_mode_shows_sms_input_before_sms_arrives(self):
        panel = ApkBackupPanel(FakeClient())
        panel._set_login_mode("phone_code")
        self.assertFalse(panel.sms_code_input.isHidden())
        self.assertFalse(panel.sms_code_input.isEnabled())

    def test_need_sms_submit_sends_phone_code_only(self):
        client = FakeClient()
        panel = ApkBackupPanel(client)
        panel._run = lambda func, ok_signal: ok_signal.emit(func())
        panel._on_session_ready({
            "sessionId": 2,
            "stage": "need_sms",
            "challenge": {"kind": "sms", "data": {"sessionKey": "phone-key-1"}},
        })
        panel.sms_code_input.setText("123456")
        panel._submit_challenge()
        self.assertEqual(client.last_challenge_payload, {"kind": "sms", "phoneCode": "123456"})

    def test_stale_captcha_callback_is_ignored_after_sms_stage(self):
        client = FakeClient()
        panel = ApkBackupPanel(client)
        panel._run = lambda func, ok_signal: ok_signal.emit(func())
        panel._on_session_ready({
            "sessionId": 2,
            "stage": "need_sms",
            "challenge": {"kind": "sms", "data": {"sessionKey": "phone-key-1"}},
        })
        panel._handle_captcha_callback({"ticket": "t", "randstr": "r", "state": panel._captcha_state})
        self.assertIsNone(client.last_challenge_payload)
        self.assertIn("短信验证码", panel.login_status.text())

    def test_normal_apk_panel_does_not_ask_for_book_or_chapter_ids(self):
        panel = ApkBackupPanel(FakeClient())
        self.assertFalse(hasattr(panel, "book_id_input"))
        self.assertFalse(hasattr(panel, "chapter_id_input"))
        self.assertIn("搜索书籍", panel.task_status.text())

    def test_authenticated_session_invokes_callback_and_guides_to_search(self):
        seen = []
        panel = ApkBackupPanel(FakeClient(), on_session_authenticated=lambda session_id: seen.append(session_id))
        panel._on_session_ready({"sessionId": 9, "stage": "authenticated", "challengeResult": {"ok": True}})
        self.assertEqual(seen, [9])
        self.assertIn("搜索书籍", panel.challenge_hint.text())


if __name__ == "__main__":
    unittest.main()
