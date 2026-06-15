import io
import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from qidian_save.adb_utils import (
    check_tar_available,
    pull_device_files_auto,
    _safe_extract_tar,
)


class TestCheckTarAvailable(unittest.TestCase):
    def test_tar_available(self):
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value="/system/bin/tar\n"):
            result = check_tar_available()
        self.assertTrue(result)

    def test_tar_unavailable(self):
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value=""):
            result = check_tar_available()
        self.assertFalse(result)

    def test_toybox_available(self):
        """Should also detect toybox as tar provider."""
        with patch("qidian_save.adb_utils.adb_shell_raw", return_value="/system/bin/toybox\n"):
            result = check_tar_available()
        self.assertTrue(result)


class TestSafeExtractTar(unittest.TestCase):
    def test_normal_extract(self):
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            tar_path = tmpdir / "test.tar"

            with tarfile.open(str(tar_path), "w") as tf:
                info = tarfile.TarInfo(name="normal.txt")
                info.size = 5
                tf.addfile(info, io.BytesIO(b"hello"))

            out_dir = tmpdir / "out"
            out_dir.mkdir()

            _safe_extract_tar(tar_path, out_dir)
            self.assertTrue((out_dir / "normal.txt").exists())
            self.assertEqual((out_dir / "normal.txt").read_text(), "hello")

    def test_path_traversal_raises(self):
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            tar_path = tmpdir / "evil.tar"

            with tarfile.open(str(tar_path), "w") as tf:
                info = tarfile.TarInfo(name="../evil.txt")
                info.size = 3
                tf.addfile(info, io.BytesIO(b"bad"))

            out_dir = tmpdir / "out"
            out_dir.mkdir()

            with self.assertRaises(ValueError):
                _safe_extract_tar(tar_path, out_dir)

    def test_absolute_path_traversal_raises(self):
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            tar_path = tmpdir / "evil2.tar"

            with tarfile.open(str(tar_path), "w") as tf:
                info = tarfile.TarInfo(name="/etc/passwd")
                info.size = 4
                tf.addfile(info, io.BytesIO(b"root"))

            out_dir = tmpdir / "out"
            out_dir.mkdir()

            with self.assertRaises(ValueError):
                _safe_extract_tar(tar_path, out_dir)

    def test_deep_traversal_raises(self):
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            tar_path = tmpdir / "evil3.tar"

            with tarfile.open(str(tar_path), "w") as tf:
                info = tarfile.TarInfo(name="out/../../evil.txt")
                info.size = 3
                tf.addfile(info, io.BytesIO(b"bad"))

            out_dir = tmpdir / "out"
            out_dir.mkdir()

            with self.assertRaises(ValueError):
                _safe_extract_tar(tar_path, out_dir)

    def test_symlink_rejected(self):
        """Symlink entries in tar must be rejected."""
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            tar_path = tmpdir / "symlink.tar"
            with tarfile.open(str(tar_path), "w") as tf:
                lnk = tarfile.TarInfo(name="evil_link")
                lnk.type = tarfile.SYMTYPE
                lnk.linkname = "/etc/passwd"
                tf.addfile(lnk)
            out_dir = tmpdir / "out"
            out_dir.mkdir()
            with self.assertRaises(ValueError):
                _safe_extract_tar(tar_path, out_dir)

    def test_adjacent_dir_bypass_raises(self):
        """../out_evil.txt where out_dir is 'out' must be rejected."""
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            tar_path = tmpdir / "adjacent_evil.tar"
            with tarfile.open(str(tar_path), "w") as tf:
                info = tarfile.TarInfo(name="../out_evil.txt")
                info.size = 3
                tf.addfile(info, io.BytesIO(b"bad"))
            out_dir = tmpdir / "out"
            out_dir.mkdir()
            with self.assertRaises(ValueError):
                _safe_extract_tar(tar_path, out_dir)


class TestPullDeviceFilesAuto(unittest.TestCase):
    def test_tar_mode_on_success(self):
        with patch("qidian_save.adb_utils.check_tar_available", return_value=True):
            with patch("qidian_save.adb_utils.pull_device_files_fast", return_value={
                "total": 10, "qdFiles": 9, "databases": 1,
                "users": [{"userId": "1", "count": 9}],
            }):
                result = pull_device_files_auto("/tmp/test")
        self.assertEqual(result.get("mode"), "tar")
        self.assertEqual(result["qdFiles"], 9)

    def test_fallback_on_tar_failure(self):
        with patch("qidian_save.adb_utils.check_tar_available", return_value=True):
            with patch("qidian_save.adb_utils.pull_device_files_fast", side_effect=Exception("tar failed")):
                with patch("qidian_save.adb_utils.pull_device_files", return_value={
                    "total": 5, "qdFiles": 4, "databases": 1,
                    "users": [{"userId": "1", "count": 4}],
                }):
                    result = pull_device_files_auto("/tmp/test")
        self.assertEqual(result.get("mode"), "legacy")
        self.assertEqual(result["qdFiles"], 4)

    def test_fallback_when_tar_unavailable(self):
        with patch("qidian_save.adb_utils.check_tar_available", return_value=False):
            with patch("qidian_save.adb_utils.pull_device_files", return_value={
                "total": 3, "qdFiles": 3, "databases": 0,
                "users": [],
            }):
                result = pull_device_files_auto("/tmp/test")
        self.assertEqual(result.get("mode"), "legacy")
        self.assertEqual(result["qdFiles"], 3)


if __name__ == "__main__":
    unittest.main()
