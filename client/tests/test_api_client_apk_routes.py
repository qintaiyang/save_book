import unittest
import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from qidian_save.api_client import QidianSaveClient


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
            "delete_apk_task",
        ]
        for name in methods:
            self.assertTrue(hasattr(QidianSaveClient, name), name)


if __name__ == "__main__":
    unittest.main()
