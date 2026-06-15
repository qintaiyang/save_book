import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from qidian_save.adb_utils import (
    find_first_typeb_seed,
    scan_typeb_seeds,
)


class TestFindFirstTypebSeed(unittest.TestCase):
    def test_parses_path_correctly(self):
        """find_first_typeb_seed should parse path into userId/bookId/chapterId."""
        mock_output = "/storage/.../book/499283868/1047226185/888754986.qd|9216\n"
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value=mock_output):
            result = find_first_typeb_seed()

        self.assertIsNotNone(result)
        self.assertEqual(result["userId"], "499283868")
        self.assertEqual(result["bookId"], "1047226185")
        self.assertEqual(result["chapterId"], "888754986")
        self.assertEqual(result["size"], 9216)
        self.assertIn("888754986.qd", result["remotePath"])

    def test_returns_none_when_no_typeb(self):
        """Empty output should return None."""
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value=""):
            result = find_first_typeb_seed()
        self.assertIsNone(result)

    def test_returns_none_on_malformed_output(self):
        """Output without pipe should return None."""
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value="just a path without pipe"):
            result = find_first_typeb_seed()
        self.assertIsNone(result)

    def test_handles_zero_size(self):
        """Should handle size=0 gracefully."""
        mock_output = "/path/book/1/2/3.qd|0\n"
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value=mock_output):
            result = find_first_typeb_seed()
        self.assertEqual(result["size"], 0)

    def test_returns_none_when_path_too_short(self):
        """Insufficient path parts (< 3 segments) should return None."""
        mock_output = "path.qd|100\n"
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value=mock_output):
            result = find_first_typeb_seed()
        self.assertIsNone(result)


class TestScanTypebSeedsFirstOnly(unittest.TestCase):
    def test_first_only_returns_single(self):
        """scan_typeb_seeds(first_only=True) should return at most 1 result."""
        mock_output = "/storage/.../book/499283868/1047226185/888754986.qd|9216\n"
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value=mock_output):
            results = scan_typeb_seeds(first_only=True)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["chapterId"], "888754986")

    def test_first_only_returns_empty_when_none(self):
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value=""):
            results = scan_typeb_seeds(first_only=True)
        self.assertEqual(len(results), 0)

    def test_first_only_false_delegates_to_full_scan(self):
        """first_only=False uses the full scan path (multiple results)."""
        mock_find = (
            "/storage/book/1/100/500.qd\n"
            "/storage/book/1/100/501.qd\n"
        )
        mock_od_header = "64"  # 0x40 = 64 decimal
        mock_size = "100"

        def _side_effect(cmd, **kwargs):
            if cmd.startswith("find"):
                return mock_find
            if cmd.startswith("dd"):
                return mock_od_header
            if cmd.startswith("stat"):
                return mock_size
            return ""

        with patch("qidian_save.adb_utils.adb_shell_raw", side_effect=_side_effect):
            results = scan_typeb_seeds(first_only=False)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["chapterId"], "500")
        self.assertEqual(results[1]["chapterId"], "501")

    def test_first_only_false_skips_non_typeb(self):
        """Non-TypeB files (header != 0x40) should be skipped."""
        mock_find = (
            "/storage/book/1/100/500.qd\n"
            "/storage/book/1/100/501.qd\n"
        )

        def _side_effect(cmd, **kwargs):
            if cmd.startswith("find"):
                return mock_find
            if cmd.startswith("dd"):
                return "0"  # header != 0x40
            if cmd.startswith("stat"):
                return "100"
            return ""

        with patch("qidian_save.adb_utils.adb_shell_raw", side_effect=_side_effect):
            results = scan_typeb_seeds(first_only=False)

        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
