"""User-configured proxy rotation for outbound Qidian requests."""
from __future__ import annotations

import threading
from collections.abc import Iterable
from urllib.parse import urlparse


SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks4", "socks5", "socks5h"}


def parse_proxy_urls(values: str | Iterable[str] | None) -> list[str]:
    """Normalize comma-separated or repeated proxy arguments."""
    if not values:
        return []
    raw_values = [values] if isinstance(values, str) else values
    result: list[str] = []
    for value in raw_values:
        for item in str(value).split(","):
            url = item.strip()
            if not url:
                continue
            parsed = urlparse(url)
            if parsed.scheme.lower() not in SUPPORTED_PROXY_SCHEMES:
                raise ValueError(f"不支持的代理协议: {parsed.scheme or url}")
            if not parsed.hostname or parsed.port is None:
                raise ValueError(f"代理地址缺少主机或端口: {url}")
            result.append(url)
    return result


class ProxyPool:
    """Thread-safe proxy selection with request-count based rotation."""

    def __init__(self, urls: str | Iterable[str] | None, rotate_every: int = 50):
        self.urls = parse_proxy_urls(urls)
        if rotate_every < 1:
            raise ValueError("代理轮换间隔必须大于 0")
        self.rotate_every = rotate_every
        self._lock = threading.Lock()
        self._request_count = 0

    def requests_proxies(self) -> dict[str, str] | None:
        if not self.urls:
            return None
        with self._lock:
            index = (self._request_count // self.rotate_every) % len(self.urls)
            self._request_count += 1
            url = self.urls[index]
        return {"http": url, "https": url}

