from pathlib import Path
import sys
import unittest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class PyprojectMetadataTests(unittest.TestCase):
    def test_python_classifiers_match_minimum_version(self):
        data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        self.assertEqual(project["requires-python"], ">=3.10")
        self.assertNotIn("Programming Language :: Python :: 3.9", project["classifiers"])


if __name__ == "__main__":
    unittest.main()
