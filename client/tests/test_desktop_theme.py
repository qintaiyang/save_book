import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.components import PageHeader, StatCard, SurfaceCard
from qidian_save.desktop.theme import DARK_TOKENS, DESIGN_TOKENS, load_qss


class DesktopThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dark_theme_exposes_required_semantic_tokens(self):
        required = {
            "bg_canvas",
            "bg_navigation",
            "surface_raised",
            "surface_inset",
            "border_subtle",
            "accent",
            "accent_highlight",
            "text_primary",
            "text_secondary",
            "success",
            "warning",
            "danger",
        }
        self.assertTrue(required <= DARK_TOKENS.keys())
        self.assertEqual(DESIGN_TOKENS["control_height"], 38)
        self.assertEqual(DESIGN_TOKENS["qt_font_family"], "Microsoft YaHei UI")

    def test_shared_components_publish_qss_properties(self):
        header = PageHeader("Search", "Find books", "LIBRARY")
        card = SurfaceCard()
        stat = StatCard("Used", "--", "accent")
        self.assertEqual(header.property("ui-role"), "page-header")
        self.assertEqual(card.property("ui-role"), "surface-card")
        self.assertEqual(stat.property("accent"), "accent")

    def test_dark_qss_styles_core_semantic_roles(self):
        qss = load_qss()
        for selector in (
            '[ui-role="page-header"]',
            '[ui-role="surface-card"]',
            '[ui-role="stat-card"]',
            '[ui-role="empty-state"]',
        ):
            self.assertIn(selector, qss)


if __name__ == "__main__":
    unittest.main()
