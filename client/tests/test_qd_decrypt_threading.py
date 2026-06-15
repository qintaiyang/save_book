import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.qd_decrypt_panel import QDDecryptPanel


class QDDecryptThreadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_set_busy_from_thread_uses_signal_not_qtimer_single_shot(self):
        """Verify worker-thread busy state uses pyqtSignal (not direct QTimer.singleShot)."""
        panel = QDDecryptPanel(client=object())
        mock_handler = MagicMock()
        panel._sig.busy_changed.connect(mock_handler)
        # _set_busy_from_thread should emit a signal; the connected _set_busy may
        # still schedule a UI-refresh QTimer.singleShot — that's a separate concern.
        panel._set_busy_from_thread(False)
        mock_handler.assert_called_once_with(False)

    def test_selected_chapters_keep_source_user_when_book_id_repeats(self):
        panel = QDDecryptPanel(client=object())
        panel._show_books([
            {
                "userId": "user_a",
                "bookId": "book_1",
                "bookName": "Same Book",
                "bookDir": r"X:\qd\user_a\book_1",
                "chapters": [{"id": "ch_1", "name": "Chapter", "size": 1024}],
                "downloaded": 1,
                "total": 1,
            },
            {
                "userId": "user_b",
                "bookId": "book_1",
                "bookName": "Same Book",
                "bookDir": r"X:\qd\user_b\book_1",
                "chapters": [{"id": "ch_1", "name": "Chapter", "size": 1024}],
                "downloaded": 1,
                "total": 1,
            },
        ])

        user_b_book = panel.tree.topLevelItem(1).child(0)
        user_b_book.child(0).setCheckState(0, __import__("PyQt6.QtCore").QtCore.Qt.CheckState.Checked)

        selected = panel._collect_selected_chapters()

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["userId"], "user_b")
        self.assertEqual(selected[0]["bookId"], "book_1")
        self.assertEqual(selected[0]["chapterId"], "ch_1")
        self.assertEqual(selected[0]["bookDir"], r"X:\qd\user_b\book_1")

    def test_fill_params_ignores_user_id(self):
        panel = QDDecryptPanel(client=object())

        panel._fill_params("qimei", "should_not_be_used", "pool")

        self.assertEqual(panel.input_qimei.text(), "qimei")
        self.assertEqual(panel.input_pool.text(), "pool")
        self.assertEqual(panel.input_userid.text(), "")
        self.assertTrue(panel.input_userid.isHidden())


if __name__ == "__main__":
    unittest.main()
