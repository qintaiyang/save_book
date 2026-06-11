import tempfile
import unittest
from pathlib import Path

from qidian_save.chapter_merge import merge_chapters


class ChapterMergeTests(unittest.TestCase):
    def test_merge_uses_catalog_order_volumes_toc_and_missing_placeholder(self):
        chapters = [
            {"chapterId": "2", "chapterName": "第二章", "volumeName": "第一卷"},
            {"chapterId": "1", "chapterName": "第一章", "volumeName": "第一卷"},
            {"chapterId": "3", "chapterName": "第三章", "volumeName": "第二卷"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2.txt").write_text("正文二", encoding="utf-8")
            (root / "1.txt").write_text("正文一", encoding="utf-8")

            output = merge_chapters(root, "测试书", chapters, include_toc=True)
            text = output.read_text(encoding="utf-8")

        self.assertLess(text.index("第二章"), text.index("第一章"))
        self.assertLess(text.index("第一章"), text.index("第三章"))
        self.assertIn("第一卷", text)
        self.assertIn("第二卷", text)
        self.assertIn("本章未保存", text)
        self.assertEqual(output.name, "测试书.txt")


if __name__ == "__main__":
    unittest.main()
