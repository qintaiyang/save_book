import io
import os
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from PyQt6.QtWidgets import QApplication

from qidian_save.advanced_backup import format_advanced_backup_error
from qidian_save.api_client import ApiError
from qidian_save.desktop.panels.advanced_backup_panel import AdvancedBackupPanel


class FakeClient:
    def __init__(self):
        self.deleted = []

    def list_advanced_backup_tasks(self, limit=50):
        return [
            {
                "taskId": 12,
                "status": "completed",
                "progressDone": 2,
                "progressTotal": 2,
                "targetRef": {
                    "bookId": 1047720448,
                    "bookName": "高级书",
                    "chapterIds": [880699692, 880699693],
                },
            }
        ]

    def get_advanced_backup_task(self, task_id):
        return {
            "taskId": task_id,
            "status": "completed",
            "progressDone": 2,
            "progressTotal": 2,
            "targetRef": {"bookName": "高级书"},
        }

    def list_advanced_backup_task_artifacts(self, task_id):
        return [{"artifactId": 5, "filename": "result.txt", "artifactType": "text", "sizeBytes": 10}]

    def download_advanced_backup_task_archive(self, task_id):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("001. 880699692.txt", "正文")
        return buf.getvalue()

    def delete_advanced_backup_task(self, task_id):
        self.deleted.append(task_id)
        return {"ok": True}


class AdvancedBackupPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_constructs_with_task_list_controls(self):
        panel = AdvancedBackupPanel(FakeClient())
        self.assertTrue(hasattr(panel, "btn_refresh_list"))
        self.assertTrue(hasattr(panel, "btn_refresh_task"))
        self.assertTrue(hasattr(panel, "btn_download"))
        self.assertTrue(hasattr(panel, "task_table"))
        self.assertIn("高级备份", panel.header.title_label.text())

    def test_refresh_list_populates_tasks_and_summary(self):
        panel = AdvancedBackupPanel(FakeClient())
        panel._run = lambda func, ok_signal: ok_signal.emit(func())

        panel.refresh_tasks()

        self.assertEqual(panel.task_table.rowCount(), 1)
        self.assertEqual(panel.task_id, 12)
        self.assertEqual(panel.stat_tasks.value.text(), "1")
        self.assertEqual(panel.stat_current.value.text(), "#12")
        self.assertTrue(panel.btn_download.isEnabled())

    def test_load_task_refreshes_status(self):
        panel = AdvancedBackupPanel(FakeClient())
        panel._run = lambda func, ok_signal: ok_signal.emit(func())

        panel.load_task(12, {"bookName": "高级书"})

        self.assertEqual(panel.task_id, 12)
        self.assertIn("completed", panel.task_status.text())
        self.assertEqual(panel.stat_progress.value.text(), "2/2")
        self.assertTrue(panel.btn_download.isEnabled())

    def test_download_archive_starts_worker_thread(self):
        panel = AdvancedBackupPanel(FakeClient())
        panel.task_id = 12
        panel._task_status = "completed"
        started = []

        class CapturedThread:
            def __init__(self, target, daemon=None):
                self.target = target
                self.daemon = daemon

            def start(self):
                started.append(self)

        with patch(
            "qidian_save.desktop.panels.advanced_backup_panel.QFileDialog.getExistingDirectory",
            return_value=str(Path.cwd()),
        ), patch(
            "qidian_save.desktop.panels.advanced_backup_panel.threading.Thread",
            CapturedThread,
        ):
            panel._download_archive()

        self.assertEqual(len(started), 1)
        self.assertFalse(panel.btn_download.isEnabled())
        self.assertIn("下载中", panel.btn_download.text())

    def test_formats_expected_advanced_backup_errors(self):
        cases = [
            (ApiError(403, {"error": "advanced_backup_disabled"}), "未开放"),
            (ApiError(403, {"error": "advanced_backup_not_allowed"}), "无权限"),
            (ApiError(503, {"error": "advanced_backup_credentials_missing"}), "服务端高级备份凭据未配置"),
            (ApiError(503, {"error": "advanced_backup_credentials_invalid"}), "服务端高级备份凭据不可用"),
            (ApiError(429, {"error": "活动任务过多，请等待已有任务完成后再试"}), "活动任务过多"),
            (ApiError(409, "任务尚未完成"), "任务尚未完成"),
        ]
        for error, expected in cases:
            self.assertIn(expected, format_advanced_backup_error(error))

    def test_error_reenables_refresh_controls(self):
        panel = AdvancedBackupPanel(FakeClient())
        panel.task_id = 12
        panel.btn_refresh_list.setEnabled(False)
        panel.btn_refresh_task.setEnabled(False)

        with patch("qidian_save.desktop.panels.advanced_backup_panel.QMessageBox.warning"):
            panel._on_error("高级备份服务暂不可用")

        self.assertTrue(panel.btn_refresh_list.isEnabled())
        self.assertTrue(panel.btn_refresh_task.isEnabled())


if __name__ == "__main__":
    unittest.main()
