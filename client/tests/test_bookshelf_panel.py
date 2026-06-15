import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.bookshelf_panel import BookshelfPanel


class FakeClient:
    def __init__(self):
        self.session_ids = []

    def get_qidian_bookshelf(self, session_id):
        self.session_ids.append(session_id)
        return {"items": [
            {"book_id": "1047226185", "book_name": "骄阳似我", "author_name": "顾漫"}
        ]}


class BookshelfPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_load_bookshelf_uses_apk_session_api(self):
        client = FakeClient()
        panel = BookshelfPanel(client, lambda *_: None, get_apk_session_id=lambda: 42)
        panel._run = lambda func, ok_signal: ok_signal.emit(func())

        panel._load_bookshelf()

        self.assertEqual(client.session_ids, [42])
        self.assertEqual(panel.table.rowCount(), 1)
        self.assertEqual(panel.table.item(0, 0).text(), "1047226185")

    def test_load_bookshelf_requires_apk_session(self):
        client = FakeClient()
        panel = BookshelfPanel(client, lambda *_: None, get_apk_session_id=lambda: 0)

        panel._load_bookshelf()

        self.assertEqual(client.session_ids, [])
        self.assertIn("登录", panel.status_label.text())


if __name__ == "__main__":
    unittest.main()
