import json
from pathlib import Path

from qidian_save.desktop.panels.qd_decrypt_panel import (
    _build_merged_book_text,
    _build_qd_zip_manifest,
    _chapter_id_from_result_name,
    _chunk_qd_files_by_size,
    _decrypted_output_name,
    _metadata_qd_entries,
    _qd_zip_arcname,
)


def test_qd_zip_arcname_includes_user_id_book_id_and_chapter_id():
    chapter = {
        "userId": "499283868",
        "bookId": "1047226185",
        "chapterId": "909754660",
    }

    assert _qd_zip_arcname(chapter) == "499283868/1047226185/909754660.qd"


def test_build_qd_zip_manifest_groups_books_and_chapters():
    chapters = [
        {
            "userId": "499283868",
            "bookId": "1047226185",
            "bookName": "骄阳似我",
            "chapterId": "461",
            "chapterName": "第471章 骄阳似我·茶艺祖师！",
        },
    ]

    manifest = _build_qd_zip_manifest(chapters)

    assert manifest == {
        "books": {
            "1047226185": {
                "bookName": "骄阳似我",
                "chapters": {"461": "第471章 骄阳似我·茶艺祖师！"},
            }
        }
    }
    json.dumps(manifest, ensure_ascii=False)


def test_metadata_qd_entries_include_book_metadata_file_once(tmp_path):
    book_dir = tmp_path / "499283868" / "1047226185"
    book_dir.mkdir(parents=True)
    meta = book_dir / "-10000.qd"
    meta.write_bytes(b"meta")
    chapters = [
        {"userId": "499283868", "bookId": "1047226185", "bookDir": str(book_dir), "chapterId": "461"},
        {"userId": "499283868", "bookId": "1047226185", "bookDir": str(book_dir), "chapterId": "462"},
    ]

    entries = _metadata_qd_entries(chapters)

    assert entries == [(Path(meta), "499283868/1047226185/-10000.qd")]


def test_chapter_id_from_result_name_supports_named_server_output():
    assert _chapter_id_from_result_name("461.txt") == "461"
    assert _chapter_id_from_result_name("461. 第471章 骄阳似我.txt") == "461"
    assert _chapter_id_from_result_name("nested/461. 第471章 骄阳似我.txt") == "461"


def test_decrypted_output_name_falls_back_to_selected_chapter_name(tmp_path):
    target = {
        "bookId": "1047226185",
        "chapterName": "第471章 骄阳似我·茶艺祖师！",
    }

    assert _decrypted_output_name("461.txt", "461", target, tmp_path) == (
        "461. 第471章 骄阳似我·茶艺祖师！.txt"
    )


def test_build_merged_book_text_includes_toc_when_enabled(tmp_path):
    chapter1 = tmp_path / "001. 第一章.txt"
    chapter2 = tmp_path / "002. 第二章.txt"
    chapter1.write_text("正文一", encoding="utf-8")
    chapter2.write_text("正文二", encoding="utf-8")

    text = _build_merged_book_text(
        "测试书",
        [chapter1, chapter2],
        include_metadata=True,
        include_toc=True,
    )

    assert "《测试书》" in text
    assert "第一章" in text
    assert "第二章" in text
    assert "正文一" in text
    assert "正文二" in text


def test_build_merged_book_text_strips_leading_metadata(tmp_path):
    chapter = tmp_path / "001. 第一章.txt"
    chapter.write_text("版权所有\nwww.example.com\n正文", encoding="utf-8")

    text = _build_merged_book_text(
        "测试书",
        [chapter],
        include_metadata=False,
        include_toc=False,
    )

    assert text == "正文"


def test_build_merged_book_text_can_add_chapter_separators(tmp_path):
    chapter1 = tmp_path / "001. 第一章.txt"
    chapter2 = tmp_path / "002. 第二章.txt"
    chapter1.write_text("正文一", encoding="utf-8")
    chapter2.write_text("正文二", encoding="utf-8")

    text = _build_merged_book_text(
        "测试书",
        [chapter1, chapter2],
        include_metadata=True,
        include_toc=False,
        include_chapter_separators=True,
    )

    assert "==================== 第一章 ====================" in text
    assert "==================== 第二章 ====================" in text
    assert "==================== 第一章 ====================\n\n正文一" in text
    assert "==================== 第二章 ====================\n\n正文二" in text


def test_chunk_qd_files_by_size_splits_before_limit(tmp_path):
    first = tmp_path / "1.qd"
    second = tmp_path / "2.qd"
    third = tmp_path / "3.qd"
    first.write_bytes(b"a" * 7)
    second.write_bytes(b"b" * 7)
    third.write_bytes(b"c" * 2)

    chunks = _chunk_qd_files_by_size(
        [
            (str(first), "u/b/1.qd"),
            (str(second), "u/b/2.qd"),
            (str(third), "u/b/3.qd"),
        ],
        max_bytes=10,
    )

    assert chunks == [
        [(str(first), "u/b/1.qd")],
        [(str(second), "u/b/2.qd"), (str(third), "u/b/3.qd")],
    ]
