import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.qidian_login_panel import QidianLoginPanel


class FakeClient:
    def get_announcements(self):
        return []


class DesktopConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_qidian_login_panel_constructs(self):
        panel = QidianLoginPanel(FakeClient())
        self.assertEqual(panel.property("ui-role"), "feature-panel")
        self.assertEqual(panel.btn_generate.property("btn-type"), "primary")
        self.assertTrue(panel.info_display.isHidden())


if __name__ == "__main__":
    unittest.main()
