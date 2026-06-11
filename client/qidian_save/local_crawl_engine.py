"""Client crawl coordinator: fetch raw data, server decode, then postprocess."""
from __future__ import annotations

import io
import json
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections.abc import Callable

from . import DATA_DIR
from .chapter_merge import merge_chapters
from .chapter_preview import fetch_previews, merge_preview_text
from .proxy import ProxyPool
from .zip_utils import safe_extract_zip


def local_crawl(
    client,
    task_id: int,
    book_id: str,
    chapters: list[dict],
    qd_cookies: dict,
    output_dir: str | None = None,
    batch_size: int = 50,
    delay: float = 1.5,
    on_progress: Callable | None = None,
    on_batch_done: Callable | None = None,
    *,
    preview_enabled: bool = False,
    merge_enabled: bool = False,
    proxy_urls: list[str] | None = None,
    proxy_rotate_every: int = 50,
    book_name: str = "",
) -> tuple[int, int]:
    """Run the local fetch -> server decode -> client postprocess pipeline."""
    if not chapters:
        return 0, 0

    resolved_book_name = (
        book_name
        or chapters[0].get("bookName")
        or f"book_{book_id}"
    )
    resolved_output = output_dir or str(
        DATA_DIR / f"{resolved_book_name}_{book_id}"
    )
    os.makedirs(resolved_output, exist_ok=True)

    preview_executor = None
    preview_future = None
    if preview_enabled:
        proxy_pool = ProxyPool(proxy_urls or [], rotate_every=proxy_rotate_every)
        preview_executor = ThreadPoolExecutor(max_workers=1)
        preview_future = preview_executor.submit(
            fetch_previews,
            book_id,
            chapters,
            proxy_pool=proxy_pool,
        )

    cookies_json = json.dumps(qd_cookies, ensure_ascii=False)
    success = 0
    failed = 0

    try:
        for batch_idx in range(0, len(chapters), batch_size):
            batch = chapters[batch_idx:batch_idx + batch_size]
            raw_data = []
            for index, chapter in enumerate(batch):
                chapter_id = str(chapter["chapterId"])
                chapter_name = chapter.get("chapterName", chapter_id)
                if on_progress:
                    on_progress(
                        batch_idx + index,
                        len(chapters),
                        f"下载 {batch_idx + index + 1}/{len(chapters)}: "
                        f"{chapter_name[:30]}",
                    )

                data = _get_chapter_data_with_fallback(
                    client, book_id, chapter_id, qd_cookies
                )
                if data:
                    raw_data.append(data)
                else:
                    failed += 1

                if index < len(batch) - 1 and delay > 0:
                    time.sleep(delay)

            if not raw_data:
                continue

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(
                zip_buffer, "w", zipfile.ZIP_DEFLATED
            ) as archive:
                for raw_chapter in raw_data:
                    archive.writestr(
                        f"{raw_chapter['chapterId']}.json",
                        json.dumps(raw_chapter, ensure_ascii=False),
                    )

            try:
                result_zip = client.decode_chapter_zip(
                    task_id, zip_buffer.getvalue(), cookies_json
                )
            except Exception as exc:
                failed += len(raw_data)
                if on_batch_done:
                    on_batch_done(0, f"服务端解码失败: {exc}")
                continue

            error_count = 0
            try:
                with zipfile.ZipFile(io.BytesIO(result_zip)) as archive:
                    if "_errors.json" in archive.namelist():
                        errors = json.loads(archive.read("_errors.json"))
                        error_count = len(errors) if isinstance(errors, list) else 0
                    safe_extract_zip(archive, resolved_output)
                batch_success = len(raw_data) - error_count
                batch_failed = error_count
            except Exception:
                batch_success = 0
                batch_failed = len(raw_data)

            success += batch_success
            failed += batch_failed
            if on_batch_done:
                message = f"批次 {batch_idx // batch_size + 1}: {batch_success} 成功"
                if batch_failed:
                    message += f", {batch_failed} 失败"
                on_batch_done(batch_success, message)

        previews = preview_future.result() if preview_future else {}
        for chapter_id, preview in previews.items():
            path = Path(resolved_output) / f"{chapter_id}.txt"
            if not path.exists():
                continue
            decoded = path.read_text(encoding="utf-8", errors="replace")
            path.write_text(
                merge_preview_text(preview, decoded),
                encoding="utf-8",
            )

        if merge_enabled:
            merge_chapters(
                resolved_output,
                resolved_book_name,
                chapters,
                include_toc=True,
            )
    finally:
        if preview_executor:
            preview_executor.shutdown(wait=False)

    return success, failed


def _get_chapter_data_with_fallback(client, book_id, chapter_id, qd_cookies):
    """Fetch one raw chapter record; all decoding remains server-side."""
    try:
        from .qidian_client import get_chapter_data

        return get_chapter_data(book_id, chapter_id, qd_cookies)
    except Exception:
        return None
