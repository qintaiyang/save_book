import sys
import unittest
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from qidian_save.api_client import QidianSaveClient


class ApiClientAdvancedBackupRouteTests(unittest.TestCase):
    def test_api_client_exposes_advanced_backup_methods(self):
        methods = [
            "create_advanced_backup_task",
            "list_advanced_backup_tasks",
            "get_advanced_backup_task",
            "list_advanced_backup_task_artifacts",
            "download_advanced_backup_artifact",
            "download_advanced_backup_task_archive",
            "delete_advanced_backup_task",
        ]
        for name in methods:
            self.assertTrue(hasattr(QidianSaveClient, name), name)

    def test_create_advanced_backup_task_posts_only_public_request_fields(self):
        client = QidianSaveClient("http://savebook.asia")
        calls = []
        client._post = lambda path, **kwargs: calls.append((path, kwargs)) or {"taskId": 9}

        result = client.create_advanced_backup_task({
            "bookId": "1047720448",
            "bookName": "测试书",
            "chapterIds": [880699692],
            "chapterNames": {"880699692": "第一章"},
            "chapters": [{"chapterId": "880699692", "chapterName": "第一章"}],
            "mergeText": True,
            "timeout": 90,
            "credentialMode": "server",
            "taskKind": "advanced_backup",
        })

        self.assertEqual(result, {"taskId": 9})
        self.assertEqual(calls[0][0], "/api/v1/advanced-backup/tasks")
        self.assertEqual(calls[0][1]["json"], {
            "bookId": 1047720448,
            "bookName": "测试书",
            "chapterIds": [880699692],
            "chapters": [{"chapterId": "880699692", "chapterName": "第一章"}],
            "mergeText": True,
            "timeout": 90,
            "wholeBook": False,
        })

    def test_list_advanced_backup_tasks_uses_filtered_endpoint(self):
        client = QidianSaveClient("http://savebook.asia")
        calls = []
        client._get = lambda path, **kwargs: calls.append((path, kwargs)) or {"items": [{"taskId": 1}]}

        self.assertEqual(client.list_advanced_backup_tasks(limit=10), [{"taskId": 1}])
        self.assertEqual(calls, [("/api/v1/advanced-backup/tasks", {"params": {"limit": 10}})])


if __name__ == "__main__":
    unittest.main()
