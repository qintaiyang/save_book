import inspect
import unittest
import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))


class SensitiveApkLogicTests(unittest.TestCase):
    def test_no_sensitive_apk_signing_logic_in_client_package(self):
        root = Path(__file__).parents[1] / "qidian_save"
        forbidden = [
            "QIMEI36",
            "QDInfo",
            "pool_b64",
            "cmfuToken",
        ]
        hits = []
        for path in [
            root / "desktop" / "panels" / "apk_backup_panel.py",
            root / "desktop" / "panels" / "__init__.py",
            root / "desktop" / "app.py",
        ]:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(token in text for token in forbidden):
                hits.append(path.name)
        self.assertEqual([], hits)

    def test_apk_panel_does_not_import_reverse_engineering_modules(self):
        from qidian_save.desktop.panels import apk_backup_panel
        source = inspect.getsource(apk_backup_panel).lower()
        self.assertNotIn("frida", source)
        self.assertNotIn("staticlogin", source)
        self.assertNotIn("getkey", source)


if __name__ == "__main__":
    unittest.main()
