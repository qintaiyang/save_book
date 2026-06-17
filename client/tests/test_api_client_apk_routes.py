import unittest
import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from qidian_save.api_client import ApiError, QidianSaveClient


class FakeResponse:
    status_code = 429
    reason = "Too Many Requests"
    url = "https://autohelp.asia/api/decrypt/qd-zip"

    def json(self):
        return {
            "detail": {
                "limit": 1000,
                "used": 900,
                "remaining": 100,
            }
        }


class ApiClientApkRouteTests(unittest.TestCase):
    def test_api_client_exposes_apk_methods(self):
        methods = [
            "create_apk_login_session",
            "get_apk_login_session",
            "submit_apk_login_challenge",
            "create_apk_backup_task",
            "get_apk_task",
            "list_apk_task_artifacts",
            "download_apk_artifact",
            "download_apk_task_archive",
            "delete_apk_task",
        ]
        for name in methods:
            self.assertTrue(hasattr(QidianSaveClient, name), name)

    def test_api_error_preserves_structured_detail(self):
        with self.assertRaises(ApiError) as ctx:
            QidianSaveClient._raise_on_error(FakeResponse())

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("日配额不足", str(ctx.exception))
        self.assertIn("remaining", str(ctx.exception))
        self.assertIn("https://autohelp.asia/api/decrypt/qd-zip", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
