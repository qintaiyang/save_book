from qidian_save.desktop.panels.qd_decrypt_panel import _qd_zip_arcname


def test_qd_zip_arcname_includes_user_id_book_id_and_chapter_id():
    chapter = {
        "userId": "499283868",
        "bookId": "1047226185",
        "chapterId": "909754660",
    }

    assert _qd_zip_arcname(chapter) == "499283868/1047226185/909754660.qd"
