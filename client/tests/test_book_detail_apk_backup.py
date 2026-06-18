import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.book_detail_panel import BookDetailPanel


class FakeClient:
    def __init__(self):
        self.last_apk_task = None
        self.upload_called = False
        self.start_backup_called = False

    def create_apk_backup_task(self, session_id, target_ref=None):
        self.last_apk_task = (session_id, target_ref)
        return {"taskId": 88}

    def upload_qidian_cookies(self, cookies):
        self.upload_called = True
        raise AssertionError("slow backup cookie upload should not run in beginner mode")

    def start_backup(self, *args, **kwargs):
        self.start_backup_called = True
        raise AssertionError("slow backup should not run in beginner mode")


class BookDetailApkBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self, session_id=7):
        client = FakeClient()
        return BookDetailPanel(
            client,
            lambda *args, **kwargs: None,
            get_apk_session_id=lambda: session_id,
            on_apk_task_started=lambda *_args, **_kwargs: None,
        ), client

    def test_apk_mode_builds_target_ref_from_selected_chapters(self):
        panel, _client = self._panel()
        panel.load_book_context("book-1", "测试书")
        panel._on_catalog({
            "authorName": "作者",
            "totalChapters": 2,
            "chapters": [
                {"chapterId": "101", "chapterName": "第一章", "isVip": False},
                {"chapterId": "202", "chapterName": "第二章", "isVip": False},
            ],
        })
        panel.chk_apk_backup.setChecked(True)
        panel.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        target_ref = panel._build_apk_target_ref([0])
        self.assertEqual(target_ref["bookId"], "book-1")
        self.assertEqual(target_ref["bookName"], "测试书")
        self.assertEqual(target_ref["chapterIds"], [101])
        self.assertEqual(target_ref["chapterNames"], {"101": "第一章"})
        self.assertEqual(
            target_ref["chapters"],
            [{"chapterId": "101", "chapterName": "第一章"}],
        )
        self.assertEqual(target_ref["downloadMode"], "batch")

    def test_apk_mode_full_selection_still_uses_explicit_chapter_ids(self):
        panel, _client = self._panel()
        panel.load_book_context("book-1", "测试书")
        panel._on_catalog({
            "authorName": "作者",
            "totalChapters": 2,
            "chapters": [
                {"chapterId": "101", "chapterName": "第一章", "isVip": False},
                {"chapterId": "202", "chapterName": "第二章", "isVip": False},
            ],
        })

        target_ref = panel._build_apk_target_ref([0, 1])

        self.assertEqual(target_ref["chapterIds"], [101, 202])
        self.assertFalse(target_ref["wholeBook"])

    def test_apk_mode_without_session_refuses_to_create_task(self):
        panel = BookDetailPanel(
            FakeClient(),
            lambda *args, **kwargs: None,
            get_apk_session_id=lambda: 0,
            on_apk_task_started=lambda *_args, **_kwargs: None,
        )
        panel._on_catalog({
            "authorName": "作者",
            "totalChapters": 1,
            "chapters": [{"chapterId": "101", "chapterName": "第一章", "isVip": False}],
        })
        panel.chk_apk_backup.setChecked(True)
        panel.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
        with patch("qidian_save.desktop.panels.book_detail_panel.QMessageBox.warning") as warn:
            panel._start_backup()
        warn.assert_called()

    def test_beginner_mode_defaults_to_fast_backup_and_skips_cookie_upload(self):
        panel, client = self._panel()
        panel.load_book_context("book-1", "测试书")
        panel._on_catalog({
            "authorName": "作者",
            "totalChapters": 1,
            "chapters": [{"chapterId": "101", "chapterName": "第一章", "isVip": False}],
        })
        panel.table.item(0, 0).setCheckState(Qt.CheckState.Checked)

        class ImmediateThread:
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                self.target()

        with patch("qidian_save.desktop.panels.book_detail_panel.threading.Thread", ImmediateThread):
            panel._start_backup()

        self.assertEqual(client.last_apk_task[0], 7)
        self.assertEqual(client.last_apk_task[1]["chapterIds"], [101])
        self.assertFalse(client.upload_called)
        self.assertFalse(client.start_backup_called)

    def test_beginner_mode_hides_slow_backup_controls(self):
        panel, _client = self._panel()
        self.assertTrue(panel.chk_apk_backup.isChecked())
        self.assertTrue(panel.chk_apk_backup.isHidden())
        self.assertTrue(panel.chk_server_crawl.isHidden())

    def test_debug_mode_shows_slow_backup_controls(self):
        panel = BookDetailPanel(
            FakeClient(),
            lambda *args, **kwargs: None,
            get_apk_session_id=lambda: 7,
            on_apk_task_started=lambda *_args, **_kwargs: None,
            debug_mode=True,
        )
        self.assertFalse(panel.chk_apk_backup.isHidden())
        self.assertFalse(panel.chk_server_crawl.isHidden())


if __name__ == "__main__":
    unittest.main()
