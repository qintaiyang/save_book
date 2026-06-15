import json
from datetime import datetime, timedelta, timezone

from qidian_save.apk_session_cache import (
    is_session_payload_reusable,
    load_cached_session,
    save_cached_session,
)


def test_save_and_load_cached_authenticated_session(tmp_path):
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    save_cached_session(
        {"sessionId": 42, "stage": "authenticated", "expiresAt": expires_at},
        path=tmp_path / "apk_session.json",
    )

    cached = load_cached_session(path=tmp_path / "apk_session.json")
    assert cached["sessionId"] == 42
    assert cached["stage"] == "authenticated"
    assert cached["expiresAt"] == expires_at


def test_cache_rejects_expired_or_unfinished_session(tmp_path):
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    assert not is_session_payload_reusable({"sessionId": 1, "stage": "authenticated", "expiresAt": expired})
    assert not is_session_payload_reusable({"sessionId": 1, "stage": "need_sms", "expiresAt": future})
    assert is_session_payload_reusable({"sessionId": 1, "stage": "authenticated", "expiresAt": future})


def test_load_cached_session_ignores_invalid_json(tmp_path):
    path = tmp_path / "apk_session.json"
    path.write_text("{broken", encoding="utf-8")

    assert load_cached_session(path=path) == {}


def test_save_cached_session_does_not_store_sensitive_fields(tmp_path):
    path = tmp_path / "apk_session.json"
    save_cached_session(
        {
            "sessionId": 42,
            "stage": "authenticated",
            "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "password": "secret",
            "loginCookieValues": {"ywkey": "sensitive"},
        },
        path=path,
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "password" not in raw
    assert "loginCookieValues" not in raw
