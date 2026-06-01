"""本地爬取引擎 — 客户端下载原始数据 → zip → 上传服务端解码 → 解压保存

被 cli.py (_cmd_backup_local_crawl) 和 backup_panel.py (_start_local_crawl) 共用。
"""
import io, json, time, zipfile, os
from pathlib import Path
from . import DATA_DIR
from .zip_utils import safe_extract_zip


def local_crawl(
    client, task_id: int, book_id: str, chapters: list[dict],
    qd_cookies: dict,
    output_dir: str = None,
    batch_size: int = 50,
    delay: float = 1.5,
    on_progress: callable = None,
    on_batch_done: callable = None,
) -> tuple[int, int]:
    """通用本地爬取引擎

    管线: batch-download → zip → decode-zip-upload → extract

    Args:
        client: QidianSaveClient 实例
        task_id: 服务端任务 ID
        book_id: 起点书籍 ID
        chapters: 要爬取的章节列表（来自 qidian_catalog 的 chapters[]）
        qd_cookies: 起点 Cookie dict
        output_dir: 输出目录（默认 DATA_DIR / <BookName>_<bookId>）
        batch_size: 每批章节数
        delay: 章节间延迟（秒）
        on_progress: 进度回调(current, total, msg)，每章调用一次
        on_batch_done: 批完成回调(count, msg)，每批完成后调用

    Returns:
        (success_count, failed_count)
    """
    if not chapters:
        return 0, 0

    cookies_json = json.dumps(qd_cookies, ensure_ascii=False)
    success = 0
    failed = 0

    for batch_idx in range(0, len(chapters), batch_size):
        batch = chapters[batch_idx:batch_idx + batch_size]

        # 4a. 下载原始数据
        raw_data = []
        for i, ch in enumerate(batch):
            cid = ch["chapterId"]
            cname = ch.get("chapterName", cid)
            msg = f"下载 {batch_idx + i + 1}/{len(chapters)}: {cname[:30]}"
            if on_progress:
                on_progress(batch_idx + i, len(chapters), msg)

            data = _get_chapter_data_with_fallback(client, book_id, cid, qd_cookies)
            if data:
                raw_data.append(data)

            if i < len(batch) - 1:
                time.sleep(delay)

        if not raw_data:
            continue

        # 4b. 打包 zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for rd in raw_data:
                zf.writestr(f"{rd['chapterId']}.json", json.dumps(rd, ensure_ascii=False))
        zip_bytes = zip_buf.getvalue()

        # 4c. 上传解码
        try:
            result_zip = client.decode_chapter_zip(task_id, zip_bytes, cookies_json)
        except Exception as e:
            if on_batch_done:
                on_batch_done(0, f"解码失败: {e}")
            failed += len(raw_data)
            continue

        # 4d. 解压保存
        if not output_dir:
            book_name = chapters[0].get("bookName", f"book_{book_id}")
            output_dir = str(DATA_DIR / f"{book_name}_{book_id}")
        os.makedirs(output_dir, exist_ok=True)

        error_count = 0
        try:
            with zipfile.ZipFile(io.BytesIO(result_zip)) as zf:
                for name in zf.namelist():
                    if name == "_errors.json":
                        errs = json.loads(zf.read(name))
                        error_count = len(errs) if isinstance(errs, list) else 0
                safe_extract_zip(zf, output_dir)
            batch_ok = len(raw_data) - error_count
            batch_fail = error_count
        except Exception:
            batch_ok = 0
            batch_fail = len(raw_data)

        success += batch_ok
        failed += batch_fail

        if on_batch_done:
            if batch_fail:
                on_batch_done(batch_ok, f"批 {batch_idx//batch_size + 1}: {batch_ok} 成功, {batch_fail} 失败")
            else:
                on_batch_done(batch_ok, f"批 {batch_idx//batch_size + 1} 完成 ({len(raw_data)} 章)")

    return success, failed


def _get_chapter_data_with_fallback(client, book_id, chapter_id, qd_cookies):
    """获取单章数据（复用 qidian_client.get_chapter_data）"""
    try:
        from .qidian_client import get_chapter_data
        return get_chapter_data(book_id, chapter_id, qd_cookies)
    except Exception:
        return None
