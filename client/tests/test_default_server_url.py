import os
import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from qidian_save import cli


def test_cli_uses_savebook_domain_by_default(monkeypatch):
    monkeypatch.delenv("QIDIAN_SAVE_URL", raising=False)
    monkeypatch.delenv("QIDIAN_SAVE_TOKEN", raising=False)
    monkeypatch.setattr(cli, "_load_token", lambda: "")

    client = cli._get_client(None)

    assert client.base_url == "http://savebook.asia"
