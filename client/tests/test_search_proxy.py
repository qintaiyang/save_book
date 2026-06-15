"""Tests for Qidian book search behavior.

Covers:
1. search_books() uses direct H5 search by default
2. search_books() can still call server API when client is explicitly provided
3. CLI search does not force the unfinished server proxy path
"""

import unittest
import sys
from argparse import Namespace
from pathlib import Path
from unittest import mock

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from qidian_save.qidian_client import search_books, _search_via_server
from qidian_save.api_client import QidianSaveClient, ApiError
from qidian_save import cli


class SearchBooksServerProxyTests(unittest.TestCase):
    """Server proxy remains available only when explicitly requested."""

    def test_calls_server_when_client_provided(self):
        client = mock.Mock(spec=QidianSaveClient)
        client._post.return_value = {
            "success": True,
            "keyword": "test",
            "items": [
                {"book_id": "42", "book_name": "Test Book", "author_name": "Author"},
            ],
            "raw_count": 1,
            "message": "",
        }

        results = search_books("test", client=client)

        client._post.assert_called_once_with(
            "/api/qidian/search",
            json={"keyword": "test", "page_index": 1, "page_size": 20},
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["bookId"], "42")
        self.assertEqual(results[0]["bookName"], "Test Book")
        self.assertEqual(results[0]["authorName"], "Author")

    def test_maps_server_fields_correctly(self):
        """Server response fields (snake_case) are mapped to old format (camelCase)."""
        client = mock.Mock(spec=QidianSaveClient)
        client._post.return_value = {
            "success": True,
            "items": [
                {
                    "book_id": "1035420986",
                    "book_name": "玄鉴仙族",
                    "author_name": "季越人",
                    "category_name": "仙侠",
                    "description": "好书",
                },
            ],
        }

        results = search_books("玄鉴", client=client)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["bookId"], "1035420986")
        self.assertEqual(results[0]["bookName"], "玄鉴仙族")
        self.assertEqual(results[0]["authorName"], "季越人")

    def test_empty_results(self):
        client = mock.Mock(spec=QidianSaveClient)
        client._post.return_value = {"success": True, "items": [], "raw_count": 0}

        results = search_books("nonexistent", client=client)
        self.assertEqual(results, [])

    def test_server_error_propagates(self):
        client = mock.Mock(spec=QidianSaveClient)
        client._post.side_effect = ApiError(502, "上游不可用")

        with self.assertRaises(ApiError):
            search_books("test", client=client)

    def test_network_error_propagates(self):
        client = mock.Mock(spec=QidianSaveClient)
        client._post.side_effect = ConnectionError("连接被拒绝")

        with self.assertRaises(ConnectionError):
            search_books("test", client=client)

    def test_fallback_to_h5_when_no_client(self):
        """Without client=, search_books uses H5 direct search."""
        with mock.patch("qidian_save.qidian_client._mobile_get") as mock_get:
            mock_get.return_value = None
            results = search_books("test")
            mock_get.assert_called_once()
            self.assertEqual(results, [])

    def test_page_param_passed_for_h5(self):
        with mock.patch("qidian_save.qidian_client._mobile_get") as mock_get:
            mock_get.return_value = None
            search_books("test", page=2)
            mock_get.assert_called_with(
                "https://m.qidian.com/search", {"kw": "test", "page": 2}
            )


class CliSearchTests(unittest.TestCase):
    def test_cli_search_uses_direct_search_without_server_client(self):
        with (
            mock.patch("qidian_save.cli._get_client") as mock_get_client,
            mock.patch("qidian_save.cli.qidian_search") as mock_search,
            mock.patch("builtins.print"),
        ):
            mock_search.return_value = [
                {"bookId": "1010868264", "bookName": "诡秘之主", "authorName": "爱潜水的乌贼"}
            ]

            cli.cmd_search(Namespace(keyword="诡秘之主"))

            mock_get_client.assert_not_called()
            mock_search.assert_called_once_with("诡秘之主")


class SearchViaServerUnitTests(unittest.TestCase):
    """_search_via_server internal logic."""

    def test_normal_mapping(self):
        client = mock.Mock(spec=QidianSaveClient)
        client._post.return_value = {
            "items": [
                {"book_id": "1", "book_name": "A", "author_name": "甲"},
                {"book_id": "2", "book_name": "B", "author_name": "乙"},
            ],
        }

        results = _search_via_server("test", client)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["bookId"], "1")
        self.assertEqual(results[1]["bookName"], "B")

    def test_missing_fields_default_to_empty(self):
        client = mock.Mock(spec=QidianSaveClient)
        client._post.return_value = {
            "items": [{"book_id": "99"}],
        }

        results = _search_via_server("test", client)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["bookId"], "99")
        self.assertEqual(results[0]["bookName"], "")
        self.assertEqual(results[0]["authorName"], "")

    def test_empty_items(self):
        client = mock.Mock(spec=QidianSaveClient)
        client._post.return_value = {"items": []}

        results = _search_via_server("test", client)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
