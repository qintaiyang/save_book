"""Public preview extraction and safe preview/body composition."""
from __future__ import annotations

import html as html_module
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable

import requests

from .proxy import ProxyPool
from .qidian_client import MOBILE_UA


_PAGE_CONTEXT_RE = re.compile(
    r'<script\s+id=["\']vite-plugin-ssr_pageContext["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _html_to_text(value: str) -> str:
    value = re.sub(r"<\s*br\s*/?\s*>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</\s*p\s*>", "\n\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html_module.unescape(value).replace("\xa0", " ")
    value = value.replace("undefined", "")
    lines = [line.strip() for line in value.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_preview_text(page_html: str) -> str:
    """Extract visible chapter content from Qidian SSR page data."""
    match = _PAGE_CONTEXT_RE.search(page_html or "")
    if not match:
        return ""
    try:
        data = json.loads(html_module.unescape(match.group(1)))
    except (json.JSONDecodeError, TypeError):
        return ""
    chapter_info = (
        data.get("pageContext", {})
        .get("pageProps", {})
        .get("pageData", {})
        .get("chapterInfo", {})
    )
    return _html_to_text(chapter_info.get("content", "") or "")


def fetch_preview(
    book_id: str,
    chapter_id: str,
    *,
    proxy_pool: ProxyPool | None = None,
    timeout: float = 15,
) -> str:
    """Fetch one public preview without sharing a requests session across threads."""
    kwargs = {
        "headers": {
            "User-Agent": MOBILE_UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
        "timeout": timeout,
    }
    if proxy_pool:
        proxies = proxy_pool.requests_proxies()
        if proxies:
            kwargs["proxies"] = proxies
    try:
        response = requests.get(
            f"https://m.qidian.com/chapter/{book_id}/{chapter_id}/",
            **kwargs,
        )
        if response.status_code != 200:
            return ""
        response.encoding = "utf-8"
        return extract_preview_text(response.text)
    except requests.RequestException:
        return ""


def fetch_previews(
    book_id: str,
    chapters: list[dict],
    *,
    proxy_pool: ProxyPool | None = None,
    max_workers: int = 8,
    fetcher: Callable = fetch_preview,
) -> dict[str, str]:
    """Fetch previews concurrently while isolating chapter-level failures."""
    result: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                fetcher,
                book_id,
                str(chapter["chapterId"]),
                proxy_pool=proxy_pool,
            ): str(chapter["chapterId"])
            for chapter in chapters
        }
        for future in as_completed(futures):
            chapter_id = futures[future]
            try:
                text = future.result()
            except Exception:
                continue
            if text:
                result[chapter_id] = text
    return result


def merge_preview_text(
    preview: str,
    decoded: str,
    *,
    min_overlap: int = 4,
) -> str:
    """Join preview and decoded text using their longest exact boundary overlap."""
    preview = (preview or "").strip()
    decoded = (decoded or "").strip()
    if not preview:
        return decoded
    if not decoded:
        return preview
    if decoded.startswith(preview) or preview in decoded:
        return decoded
    if preview.endswith(decoded):
        return preview

    max_overlap = min(len(preview), len(decoded))
    for size in range(max_overlap, min_overlap - 1, -1):
        if preview[-size:] == decoded[:size]:
            return preview + decoded[size:]
    return f"{preview}\n\n{decoded}"
