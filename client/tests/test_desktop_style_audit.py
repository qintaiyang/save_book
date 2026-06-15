import unittest
from pathlib import Path


DESKTOP = Path(__file__).parents[1] / "qidian_save" / "desktop"
UI_SOURCES = list((DESKTOP / "panels").glob("*.py")) + [
    DESKTOP / "widgets" / "reader.py",
]


class DesktopStyleAuditTests(unittest.TestCase):
    def test_panels_do_not_embed_color_styles(self):
        offenders = []
        for path in UI_SOURCES:
            source = path.read_text(encoding="utf-8")
            if "setStyleSheet(" in source:
                offenders.append(path.name)
        self.assertEqual([], offenders)

    def test_feature_panels_use_shared_page_headers(self):
        expected = {
            "search_panel.py",
            "qidian_login_panel.py",
            "bookshelf_panel.py",
            "book_detail_panel.py",
            "backup_panel.py",
            "apk_backup_panel.py",
            "qd_decrypt_panel.py",
            "usage_panel.py",
        }
        missing = []
        for name in expected:
            source = (DESKTOP / "panels" / name).read_text(encoding="utf-8")
            if "PageHeader(" not in source:
                missing.append(name)
        self.assertEqual([], missing)

    def test_structural_emoji_are_not_used_in_controls(self):
        offenders = []
        for path in UI_SOURCES:
            source = path.read_text(encoding="utf-8")
            if any(char in source for char in ("📖", "📄", "👤", "🌙", "☀️")):
                offenders.append(path.name)
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
