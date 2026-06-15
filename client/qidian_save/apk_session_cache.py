"""Local cache for server-side APK login session references.

The desktop client is open source, so this file deliberately stores only the
server session id and expiry metadata. Qidian cookies, passwords, and reverse
signing material stay on the server.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import DATA_DIR

APK_SESSION_CACHE_FILE = DATA_DIR / "apk_session.json"
_ALLOWED_KEYS = {"sessionId", "stage", "expiresAt"}


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_session_payload_reusable(payload: dict[str, Any], now: datetime | None = None) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        session_id = int(payload.get("sessionId") or 0)
    except (TypeError, ValueError):
        return False
    if session_id <= 0 or payload.get("stage") != "authenticated":
        return False
    expires_at = _parse_datetime(payload.get("expiresAt"))
    if expires_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return expires_at > current.astimezone(timezone.utc)


def load_cached_session(path: str | Path = APK_SESSION_CACHE_FILE) -> dict[str, Any]:
    cache_path = Path(path)
    if not cache_path.exists():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: payload[key] for key in _ALLOWED_KEYS if key in payload}


def save_cached_session(payload: dict[str, Any], path: str | Path = APK_SESSION_CACHE_FILE) -> None:
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    safe_payload = {key: payload[key] for key in _ALLOWED_KEYS if key in payload}
    cache_path.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        cache_path.chmod(0o600)
    except OSError:
        pass


def clear_cached_session(path: str | Path = APK_SESSION_CACHE_FILE) -> None:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
