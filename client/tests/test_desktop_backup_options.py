import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.book_detail_panel import BookDetailPanel
from qidian_save.desktop.panels.backup_panel import BackupPanel


class DesktopBackupOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_detail_panel_exposes_preview_merge_and_proxy_options(self):
        panel = BookDetailPanel(object(), lambda *_args: None)
        panel.proxy_input.setText(
            "http://one.example:8080, socks5://two.example:1080"
        )
        options = panel._backup_options()
        self.assertTrue(options["preview_enabled"])
        self.assertTrue(options["merge_enabled"])
        self.assertEqual(options["proxy_urls"], [
            "http://one.example:8080",
            "socks5://two.example:1080",
        ])

    def test_server_download_postprocess_merges_preview_and_book(self):
        panel = BackupPanel(object())
        panel._book_id = "book"
        panel._qd_cookies = {}
        panel._backup_options = {
            "preview_enabled": True,
            "merge_enabled": True,
            "proxy_urls": [],
            "proxy_rotate_every": 50,
        }
        panel.task_info = {"bookName": "测试书"}
        chapters = [{
            "chapterId": "1",
            "chapterName": "第一章",
            "volumeName": "正文卷",
        }]

        with tempfile.TemporaryDirectory() as tmp, \
             patch(
                 "qidian_save.qidian_client.get_catalog",
                 return_value={"bookName": "测试书", "chapters": chapters},
             ), \
             patch(
                 "qidian_save.chapter_preview.fetch_previews",
                 return_value={"1": "公开试读\n共同结尾"},
             ):
            panel._download_dir = tmp
            (Path(tmp) / "1.txt").write_text(
                "共同结尾\n服务端正文", encoding="utf-8"
            )
            panel._postprocess_server_download(chapters)
            chapter_text = (Path(tmp) / "1.txt").read_text(encoding="utf-8")
            book_text = (Path(tmp) / "测试书.txt").read_text(encoding="utf-8")

        self.assertEqual(chapter_text.count("共同结尾"), 1)
        self.assertIn("公开试读", book_text)
        self.assertIn("服务端正文", book_text)


if __name__ == "__main__":
    unittest.main()
