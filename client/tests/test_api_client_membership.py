import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from qidian_save.api_client import QidianSaveClient


class FakeResponse:
    status_code = 200
    reason = "OK"
    url = "http://example.test"
    content = b""

    def __init__(self, payload=None):
        self._payload = payload or {"ok": True}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return FakeResponse({"membership": True})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return FakeResponse({"ok": True})

    def mount(self, *_args, **_kwargs):
        pass


def make_client():
    client = QidianSaveClient("http://server.test")
    client.session = FakeSession()
    return client


def test_register_sends_invite_code_alias():
    client = make_client()

    client.register("10000@qq.com", "password123", "reader", invite_code="INVITE-001")

    assert client.session.calls == [
        (
            "POST",
            "http://server.test/auth/register",
            {
                "json": {
                    "email": "10000@qq.com",
                    "password": "password123",
                    "username": "reader",
                    "inviteCode": "INVITE-001",
                },
                "timeout": 30,
            },
        )
    ]


def test_membership_and_card_routes_use_portal_api():
    client = make_client()

    client.get_membership()
    client.bind_card("CARD-ABC")
    client.unbind_card()

    assert [call[:2] for call in client.session.calls] == [
        ("GET", "http://server.test/api/me/membership"),
        ("POST", "http://server.test/api/me/cards/bind"),
        ("POST", "http://server.test/api/me/cards/unbind"),
    ]
    assert client.session.calls[1][2]["json"] == {"code": "CARD-ABC"}
