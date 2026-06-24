from pathlib import Path
import sys
import unittest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]


class PyprojectMetadataTests(unittest.TestCase):
    def test_python_classifiers_match_minimum_version(self):
        data = tomllib.loads((ROOT / "client" / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        self.assertEqual(project["requires-python"], ">=3.10")
        self.assertNotIn("Programming Language :: Python :: 3.9", project["classifiers"])

    def test_release_metadata_points_to_savebook_domain(self):
        data = tomllib.loads((ROOT / "client" / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        self.assertEqual(project["version"], "1.3.5")
        self.assertEqual(project["urls"]["Homepage"], "http://savebook.asia/")
        self.assertEqual(project["urls"]["Documentation"], "http://savebook.asia/docs")


if __name__ == "__main__":
    unittest.main()
