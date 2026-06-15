"""Repository-root launcher shim for the client package.

This keeps ``python -m qidian_save ...`` from the repository root bound to
``client/qidian_save`` instead of an older editable install elsewhere.
"""
from pathlib import Path

_CLIENT_PACKAGE = Path(__file__).resolve().parent.parent / "client" / "qidian_save"
__path__ = [str(_CLIENT_PACKAGE)]

# Match client/qidian_save/__init__.py so relative imports see the same data dir.
DATA_DIR = _CLIENT_PACKAGE.parent / "data"
