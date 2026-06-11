import unittest

from qidian_save.chapter_preview import (
    extract_preview_text,
    fetch_previews,
    merge_preview_text,
)


class ChapterPreviewTests(unittest.TestCase):
    def test_extract_preview_text_reads_ssr_json_and_normalizes_html(self):
        html = """
        <script id="vite-plugin-ssr_pageContext">
        {"pageContext":{"pageProps":{"pageData":{"chapterInfo":{
          "content":"<p>第一段&nbsp;内容</p><p>第二段<br>下一行</p>"
        }}}}}
        </script>
        """
        self.assertEqual(
            extract_preview_text(html),
            "第一段 内容\n\n第二段\n下一行",
        )

    def test_merge_preview_removes_shared_boundary(self):
        preview = "开头内容\n共同段落甲乙丙丁"
        decoded = "共同段落甲乙丙丁\n后续付费内容"
        merged = merge_preview_text(preview, decoded, min_overlap=6)
        self.assertEqual(merged, "开头内容\n共同段落甲乙丙丁\n后续付费内容")

    def test_merge_preview_does_not_duplicate_when_decoded_contains_preview(self):
        preview = "完整试读内容"
        decoded = "完整试读内容\n后续正文"
        self.assertEqual(merge_preview_text(preview, decoded), decoded)

    def test_fetch_previews_isolates_individual_failures(self):
        chapters = [
            {"chapterId": "1"},
            {"chapterId": "2"},
            {"chapterId": "3"},
        ]

        def fake_fetch(_book_id, chapter_id, **_kwargs):
            if chapter_id == "2":
                raise RuntimeError("network")
            return f"text-{chapter_id}" if chapter_id == "1" else ""

        result = fetch_previews("book", chapters, fetcher=fake_fetch, max_workers=2)
        self.assertEqual(result, {"1": "text-1"})


if __name__ == "__main__":
    unittest.main()
