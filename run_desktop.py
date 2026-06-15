"""Start the desktop app from the repository root using local client sources."""
from pathlib import Path
import sys

CLIENT_DIR = Path(__file__).resolve().parent / "client"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from qidian_save.desktop.app import main

if __name__ == "__main__":
    main()
