import os
import unittest
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.apk_backup_panel import ApkBackupPanel


class FakeClient:
    base_url = "http://127.0.0.1:8765"

    def get_apk_task(self, task_id):
        return {"taskId": task_id, "status": "completed", "progressDone": 1, "progressTotal": 1}

    def list_apk_task_artifacts(self, task_id):
        return [{"artifactId": 11, "filename": "chapter.txt", "artifactType": "text", "sizeBytes": 100}]

    def download_apk_artifact(self, task_id, artifact_id):
        return b"chapter content"


class ApkBackupPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_title_says_online_backup(self):
        panel = ApkBackupPanel(FakeClient())
        from PyQt6.QtWidgets import QLabel
        labels = [child.text() for child in panel.findChildren(QLabel)]
        joined = "\n".join(labels)
        self.assertIn("在线备份", joined)
        self.assertNotIn("快速备份", joined)

    def test_panel_has_no_login_forms(self):
        panel = ApkBackupPanel(FakeClient())
        # No account/password/sms/captcha inputs in normal mode
        self.assertFalse(hasattr(panel, "account_input"))
        self.assertFalse(hasattr(panel, "password_input"))
        self.assertFalse(hasattr(panel, "sms_code_input"))
        self.assertFalse(hasattr(panel, "challenge_input"))
        self.assertFalse(hasattr(panel, "btn_create_session"))
        self.assertFalse(hasattr(panel, "btn_submit_sms"))

    def test_panel_has_refresh_and_download_buttons(self):
        panel = ApkBackupPanel(FakeClient())
        self.assertTrue(hasattr(panel, "btn_refresh"))
        self.assertTrue(hasattr(panel, "btn_download"))

    def test_panel_has_compact_status_summary(self):
        panel = ApkBackupPanel(FakeClient())
        self.assertTrue(hasattr(panel, "stat_login"))
        self.assertTrue(hasattr(panel, "stat_task"))
        self.assertTrue(hasattr(panel, "stat_progress"))
        self.assertIn("未登录", panel.stat_login.value.text())
        self.assertIn("无任务", panel.stat_task.value.text())

    def test_panel_shows_no_task_state_initially(self):
        panel = ApkBackupPanel(FakeClient())
        self.assertIn("没有正在进行的任务", panel.task_status.text())

    def test_load_task_enables_refresh(self):
        panel = ApkBackupPanel(FakeClient())
        panel.load_task(42)
        self.assertEqual(panel.task_id, 42)

    def test_task_refresh_updates_status(self):
        panel = ApkBackupPanel(FakeClient())
        panel._run = lambda func, ok_signal: ok_signal.emit(func())
        panel.load_task(42)
        self.assertIn("completed", panel.task_status.text())
        self.assertEqual(panel.stat_task.value.text(), "completed")
        self.assertEqual(panel.stat_progress.value.text(), "1/1")

    def test_artifacts_enable_download(self):
        panel = ApkBackupPanel(FakeClient())
        panel.task_id = 42
        self.assertFalse(panel.btn_download.isEnabled())
        panel._on_artifacts_ready([{"artifactId": 11, "filename": "c.txt"}])
        self.assertTrue(panel.btn_download.isEnabled())

    def test_login_offline_shows_prompt(self):
        panel = ApkBackupPanel(FakeClient())
        panel.set_login_online(False)
        self.assertIn("请先到", panel.login_status_label.text())

    def test_login_online_shows_online(self):
        panel = ApkBackupPanel(FakeClient())
        panel.set_login_online(True)
        self.assertIn("已登录", panel.login_status_label.text())
        self.assertIn("已登录", panel.stat_login.value.text())

    def test_artifact_table_hidden_in_normal_mode(self):
        panel = ApkBackupPanel(FakeClient())
        self.assertTrue(panel.artifact_card.isHidden())

    def test_artifact_table_visible_in_debug_mode(self):
        panel = ApkBackupPanel(FakeClient(), debug_mode=True)
        self.assertFalse(panel.artifact_card.isHidden())

    def test_completed_task_enables_download(self):
        panel = ApkBackupPanel(FakeClient())
        panel._on_task_ready({"taskId": 42, "status": "completed", "progressDone": 1, "progressTotal": 1})
        self.assertTrue(panel.btn_download.isEnabled())

    def test_non_completed_task_disables_download(self):
        panel = ApkBackupPanel(FakeClient())
        panel._on_task_ready({"taskId": 42, "status": "queued", "progressDone": 0, "progressTotal": 3})
        self.assertFalse(panel.btn_download.isEnabled())

    def test_set_login_online_from_main_window(self):
        panel = ApkBackupPanel(FakeClient())
        panel.set_login_online(True)
        self.assertIn("已登录", panel.login_status_label.text())
        panel.set_login_online(False)
        self.assertIn("请先到", panel.login_status_label.text())


if __name__ == "__main__":
    unittest.main()
