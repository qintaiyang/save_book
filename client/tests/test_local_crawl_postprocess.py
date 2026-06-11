import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from qidian_save.local_crawl_engine import local_crawl


class FakeDecodeClient:
    def decode_chapter_zip(self, _task_id, zip_data, _cookies):
        with zipfile.ZipFile(io.BytesIO(zip_data)) as source:
            chapter_ids = [
                Path(name).stem for name in source.namelist()
                if name.endswith(".json")
            ]
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for chapter_id in chapter_ids:
                target.writestr(f"{chapter_id}.txt", "共同结尾\n服务端正文")
        return output.getvalue()


class LocalCrawlPostprocessTests(unittest.TestCase):
    def test_local_crawl_merges_preview_and_creates_book_file(self):
        chapters = [{
            "chapterId": "1",
            "chapterName": "第一章",
            "bookName": "测试书",
            "volumeName": "正文卷",
        }]
        raw = {
            "chapterId": "1",
            "chapterName": "第一章",
            "content": "raw",
        }
        with tempfile.TemporaryDirectory() as tmp, \
             patch("qidian_save.local_crawl_engine._get_chapter_data_with_fallback",
                   return_value=raw), \
             patch("qidian_save.local_crawl_engine.fetch_previews",
                   return_value={"1": "公开试读\n共同结尾"}):
            success, failed = local_crawl(
                FakeDecodeClient(), 7, "book", chapters, {},
                output_dir=tmp,
                batch_size=1,
                delay=0,
                preview_enabled=True,
                merge_enabled=True,
                book_name="测试书",
            )
            chapter_text = (Path(tmp) / "1.txt").read_text(encoding="utf-8")
            merged_text = (Path(tmp) / "测试书.txt").read_text(encoding="utf-8")

        self.assertEqual((success, failed), (1, 0))
        self.assertEqual(chapter_text.count("共同结尾"), 1)
        self.assertIn("公开试读", merged_text)
        self.assertIn("服务端正文", merged_text)


if __name__ == "__main__":
    unittest.main()
