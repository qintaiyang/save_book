# Code Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the concrete defects found in the review without broad rewrites, UI redesign, service-side changes, or unrelated cleanup.

**Architecture:** Keep the current client architecture intact. Add small helper functions where they reduce repeated risk, especially zip extraction and UI thread handoff. Preserve existing public CLI commands and desktop panel behavior except where this plan explicitly changes broken behavior.

**Tech Stack:** Python 3, argparse, requests, PyQt6, PyQt6-Fluent-Widgets, unittest, ruff.

---

## Hard Rules For DeepSeek

Read this section before editing any file.

- Do not modify `qidian_save--server/` or any sibling repository.
- Do not edit generated artifacts: `client/build/`, `client/dist/`, `client/dist-exe/`, `client/qidian_save.egg-info/`, `client/data/`, `client/qd_files/`, root `*.zip`.
- Do not reformat the whole project.
- Do not rename commands, panels, classes, or public methods unless this plan says so.
- Do not change API endpoint paths, request body field names, auth headers, or cookie file locations.
- Do not add new runtime dependencies.
- Do not add broad exception swallowing to hide failures.
- Do not claim completion unless every command in the final verification section has been run and the output matches the expected result.
- If a step fails, stop and report the exact command and output. Do not invent a workaround.

## Current Verified Failures

These failures were observed before writing this plan:

- `python -m qidian_save adb-db` fails with `NameError: name 'Path' is not defined`.
- `python -m qidian_save decrypt does-not-exist.qd --qimei36 x --user-id y --pool-b64 z` fails with `NameError: name 'Path' is not defined`.
- `python -m ruff check client\qidian_save` reports 62 issues, including `F821 Undefined name Path` and `F821 Undefined name QStackedWidget`.
- `python -m unittest discover -s .` runs 0 tests.

## Files To Modify

- Modify `client/qidian_save/cli.py`
  - Add missing `Path` import.
  - Stop ADB commands when multiple devices require explicit `--device`.
  - Use safe zip extraction for CLI decode/decrypt results.
- Modify `client/qidian_save/desktop/app.py`
  - Remove or fix the undefined `QStackedWidget` annotation.
  - Move usage refresh off the UI thread.
- Modify `client/qidian_save/desktop/panels/backup_panel.py`
  - Add real polling timer for server-side backup tasks.
  - Use safe zip extraction for local crawl decoded zip output.
- Modify `client/qidian_save/desktop/panels/login_panel.py`
  - Route all poll status updates through signals instead of direct UI writes from a worker thread.
- Modify `client/qidian_save/desktop/panels/qd_decrypt_panel.py`
  - Route root parameter UI updates through signals instead of `QTimer.singleShot` from worker threads.
  - Use safe zip extraction for decrypt result zip output.
- Modify `client/qidian_save/desktop/panels/qidian_login_panel.py`
  - Fetch announcements in a worker thread, not directly on the UI thread.
- Create `client/qidian_save/zip_utils.py`
  - Provide one shared safe extraction helper.
- Create tests under `client/tests/`
  - Add regression tests for CLI `Path` failures, multi-device abort, safe zip extraction, and basic polling behavior.
- Modify `.gitignore`
  - Ignore root release zips and `client/dist-exe/`.

## Task 1: Add Safe Zip Extraction Helper

**Files:**
- Create: `client/qidian_save/zip_utils.py`
- Create: `client/tests/test_zip_utils.py`

- [ ] **Step 1: Create the failing tests**

Create `client/tests/test_zip_utils.py`:

```python
import io
import zipfile
from pathlib import Path
import unittest

from qidian_save.zip_utils import UnsafeZipPathError, safe_extract_zip


class SafeExtractZipTests(unittest.TestCase):
    def _zip_bytes(self, entries):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in entries.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_extracts_normal_relative_files(self):
        data = self._zip_bytes({"book/1.txt": "hello"})
        out = Path(self._tmp.name) / "out"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            extracted = safe_extract_zip(zf, out)
        self.assertEqual((out / "book" / "1.txt").read_text(encoding="utf-8"), "hello")
        self.assertEqual(extracted, [out / "book" / "1.txt"])

    def test_rejects_parent_directory_escape(self):
        data = self._zip_bytes({"../escape.txt": "bad"})
        out = Path(self._tmp.name) / "out"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            with self.assertRaises(UnsafeZipPathError):
                safe_extract_zip(zf, out)

    def test_rejects_absolute_path(self):
        data = self._zip_bytes({"/absolute.txt": "bad"})
        out = Path(self._tmp.name) / "out"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            with self.assertRaises(UnsafeZipPathError):
                safe_extract_zip(zf, out)

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run from `client/`:

```powershell
python -m unittest tests.test_zip_utils -v
```

Expected: FAIL or ERROR because `qidian_save.zip_utils` does not exist.

- [ ] **Step 3: Implement the helper**

Create `client/qidian_save/zip_utils.py`:

```python
"""Utilities for safely extracting zip files returned by the server."""
from pathlib import Path
import zipfile


class UnsafeZipPathError(ValueError):
    """Raised when a zip member would extract outside the target directory."""


def _safe_member_path(output_dir: Path, member_name: str) -> Path:
    target_root = output_dir.resolve()
    member_path = Path(member_name)

    if member_path.is_absolute():
        raise UnsafeZipPathError(f"Unsafe absolute zip path: {member_name}")

    target = (target_root / member_path).resolve()
    if target != target_root and target_root not in target.parents:
        raise UnsafeZipPathError(f"Unsafe zip path traversal: {member_name}")
    return target


def safe_extract_zip(zf: zipfile.ZipFile, output_dir: str | Path) -> list[Path]:
    """Extract all zip members after verifying they stay under output_dir."""
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    extracted: list[Path] = []
    for info in zf.infolist():
        target = _safe_member_path(output_root, info.filename)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, target.open("wb") as dst:
            dst.write(src.read())
        extracted.append(target)
    return extracted
```

- [ ] **Step 4: Run the test and confirm it passes**

Run from `client/`:

```powershell
python -m unittest tests.test_zip_utils -v
```

Expected: 3 tests pass.

## Task 2: Fix CLI `Path` Crashes And Multi-Device Abort

**Files:**
- Modify: `client/qidian_save/cli.py`
- Create: `client/tests/test_cli_regressions.py`

- [ ] **Step 1: Create regression tests**

Create `client/tests/test_cli_regressions.py`:

```python
import argparse
import unittest
from unittest.mock import patch

from qidian_save import cli


class CliRegressionTests(unittest.TestCase):
    def test_cmd_decrypt_uses_path_import_and_reaches_file_check(self):
        args = argparse.Namespace(
            file="does-not-exist.qd",
            qimei36="x",
            user_id="y",
            pool_b64="z",
            output=None,
        )
        with patch.object(cli, "_get_client") as get_client:
            client = get_client.return_value
            client.decrypt_qd.side_effect = FileNotFoundError("missing")
            with self.assertRaises(FileNotFoundError):
                cli.cmd_decrypt(args)

    def test_cmd_adb_db_uses_path_import_and_handles_missing_dir(self):
        args = argparse.Namespace(dir="definitely-missing-dir")
        with patch("builtins.print") as fake_print:
            cli.cmd_adb_db(args)
        printed = "\n".join(str(call.args[0]) for call in fake_print.call_args_list if call.args)
        self.assertIn("definitely-missing-dir", printed)

    def test_adb_scan_aborts_when_device_resolution_requires_user_choice(self):
        args = argparse.Namespace(device=None)
        with patch.object(cli, "_resolve_device", return_value=None), \
             patch.object(cli, "list_devices", return_value=[
                 {"serial": "one", "status": "device"},
                 {"serial": "two", "status": "device"},
             ]), \
             patch.object(cli, "check_device", return_value=True), \
             patch.object(cli, "scan_device") as scan_device:
            cli.cmd_adb_scan(args)
        scan_device.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and confirm at least the decrypt/db tests fail before the fix**

Run from `client/`:

```powershell
python -m unittest tests.test_cli_regressions -v
```

Expected before implementation: errors related to `Path` not defined, or the multi-device test calls `scan_device`.

- [ ] **Step 3: Implement the CLI fixes**

In `client/qidian_save/cli.py`:

1. Add this import near the existing imports:

```python
from pathlib import Path
```

2. Import the safe zip helper:

```python
from .zip_utils import safe_extract_zip
```

3. In `cmd_adb_scan`, `cmd_adb_pull`, and `cmd_adb_extract`, immediately after `serial = _resolve_device(args.device)`, add this guard:

```python
    if serial is None and len(list_devices()) > 1:
        return
```

4. Replace CLI zip extraction:

In local crawl extraction, replace:

```python
                    zf.extract(name, output_dir)
```

with:

```python
                    safe_extract_zip(zf, output_dir)
                    break
```

Do not extract `_errors.json` as a content file. Keep the existing `_errors.json` parsing behavior before extraction. The safest implementation is:

```python
            with zipfile.ZipFile(io.BytesIO(result_zip)) as zf:
                for name in zf.namelist():
                    if name == "_errors.json":
                        errors_data = json.loads(zf.read(name))
                        error_chapters = errors_data if isinstance(errors_data, list) else []
                content_names = [n for n in zf.namelist() if n != "_errors.json"]
                if content_names:
                    safe_extract_zip(zf, output_dir)
```

If `safe_extract_zip` would also extract `_errors.json`, adjust `safe_extract_zip` call by creating a filtered helper loop locally. Do not leave unsafe `extract` calls.

5. Replace:

```python
        with zipfile.ZipFile(result_zip, "r") as zf:
            zf.extractall(str(extract_dir))
```

with:

```python
        with zipfile.ZipFile(result_zip, "r") as zf:
            safe_extract_zip(zf, extract_dir)
```

- [ ] **Step 4: Run focused CLI tests**

Run from `client/`:

```powershell
python -m unittest tests.test_cli_regressions -v
```

Expected: all tests pass.

## Task 3: Fix Desktop Backup Polling

**Files:**
- Modify: `client/qidian_save/desktop/panels/backup_panel.py`
- Create: `client/tests/test_backup_panel_polling.py`

- [ ] **Step 1: Create a focused polling test**

Create `client/tests/test_backup_panel_polling.py`:

```python
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.backup_panel import BackupPanel


class FakeClient:
    def __init__(self):
        self.calls = 0

    def get_task(self, task_id):
        self.calls += 1
        return {
            "bookName": "Book",
            "bookId": "1",
            "status": "running",
            "totalChapters": 10,
            "completedChapters": 1,
            "failedChapters": 0,
        }


class BackupPanelPollingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_server_task_starts_timer(self):
        client = FakeClient()
        panel = BackupPanel(client)
        panel.load_task(123, server_crawl=True)
        self.assertTrue(panel._polling)
        self.assertTrue(panel._poll_timer.isActive())
        panel._poll_timer.stop()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm it fails before the fix**

Run from `client/`:

```powershell
python -m unittest tests.test_backup_panel_polling -v
```

Expected before implementation: `BackupPanel` has no `_poll_timer`, or timer is not active.

- [ ] **Step 3: Implement polling timer**

In `client/qidian_save/desktop/panels/backup_panel.py`:

1. Keep `QTimer` import.
2. In `__init__`, after signal setup and before `_init_ui()` or after `_init_ui()`, create:

```python
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_task)
```

3. Replace `_start_polling` with:

```python
    def _start_polling(self):
        if self._polling:
            return
        self._polling = True
        self._poll_task()
        self._poll_timer.start(3000)
```

4. In `_poll_task`, when terminal status is reached, stop the timer:

```python
            if status["status"] in ("completed", "failed"):
                self._polling = False
                self._poll_timer.stop()
```

5. In `_cleanup`, stop the timer:

```python
            self._polling = False
            self._poll_timer.stop()
```

- [ ] **Step 4: Run the polling test**

Run from `client/`:

```powershell
python -m unittest tests.test_backup_panel_polling -v
```

Expected: test passes.

## Task 4: Replace Unsafe Desktop Zip Extraction

**Files:**
- Modify: `client/qidian_save/desktop/panels/backup_panel.py`
- Modify: `client/qidian_save/desktop/panels/qd_decrypt_panel.py`

- [ ] **Step 1: Import helper**

In both files, add:

```python
from ...zip_utils import safe_extract_zip
```

Use the correct relative import level. These panel files live under `qidian_save/desktop/panels/`, so `...zip_utils` is correct.

- [ ] **Step 2: Replace extraction in `backup_panel.py`**

Replace:

```python
                                zf.extract(name, output_dir)
```

with a safe extraction approach. Preserve `_errors.json` parsing. The accepted pattern is:

```python
                            for name in zf.namelist():
                                if name == "_errors.json":
                                    errs = json.loads(zf.read(name))
                                    failed += len(errs) if isinstance(errs, list) else 0
                            safe_extract_zip(zf, output_dir)
```

If `_errors.json` is extracted too, that is acceptable only if it stays inside `output_dir`. Do not use `extract` or `extractall`.

- [ ] **Step 3: Replace extraction in `qd_decrypt_panel.py`**

Replace:

```python
                with zipfile.ZipFile(result_zip, "r") as zf:
                    zf.extractall(extract_dir)
```

with:

```python
                with zipfile.ZipFile(result_zip, "r") as zf:
                    safe_extract_zip(zf, extract_dir)
```

- [ ] **Step 4: Verify no unsafe extraction remains in source**

Run from repo root:

```powershell
Select-String -Path client\qidian_save\*.py,client\qidian_save\desktop\panels\*.py -Pattern "extractall|\.extract\("
```

Expected: no matches for unsafe zip extraction. It is OK if the only matches are in comments explaining removal.

## Task 5: Fix Qt Thread-Safety Violations

**Files:**
- Modify: `client/qidian_save/desktop/panels/login_panel.py`
- Modify: `client/qidian_save/desktop/panels/qd_decrypt_panel.py`
- Modify: `client/qidian_save/desktop/panels/qidian_login_panel.py`
- Modify: `client/qidian_save/desktop/app.py`

- [ ] **Step 1: Fix `login_panel.py` worker UI writes**

Add a signal to `_LoginSignal`:

```python
    status_update = pyqtSignal(str, bool)
```

Connect it in `LoginPanel.__init__`:

```python
        self._sig.status_update.connect(self._set_status)
```

In `_start_polling`, replace direct `_set_status(...)` calls inside `_poll()` with signal emits:

```python
self._sig.status_update.emit("登录已过期，请重新点击登录", True)
self._sig.status_update.emit("用户取消了授权", True)
self._sig.status_update.emit("等待授权中...", False)
```

Use the existing Chinese text if desired, but the important rule is: no direct widget updates from `_poll()`.

- [ ] **Step 2: Fix `qd_decrypt_panel.py` root extract UI writes**

Add a signal to `_DecryptSignal`:

```python
    params_ready = pyqtSignal(str, str, str)
```

Connect it in `QDDecryptPanel.__init__`:

```python
        self._sig.params_ready.connect(self._fill_params)
```

Add method:

```python
    def _fill_params(self, qimei36: str, user_id: str, pool_b64: str):
        if qimei36:
            self.input_qimei.setText(qimei36)
        if user_id:
            self.input_userid.setText(user_id)
        if pool_b64:
            self.input_pool.setText(pool_b64)
```

Replace the three `QTimer.singleShot(0, lambda...)` calls in `_root_extract` with:

```python
                    self._sig.params_ready.emit(qimei36, user_id, pool_b64)
```

- [ ] **Step 3: Move announcements off UI thread**

In `qidian_login_panel.py`, replace `QTimer.singleShot(0, self._refresh_announcements)` with a worker thread.

Add signal:

```python
    announcements_ready = pyqtSignal(list)
```

Connect it:

```python
        self._sig.announcements_ready.connect(self._on_announcements_ready)
```

Change `_refresh_announcements` so it only does network work in a thread:

```python
    def _refresh_announcements(self):
        def _run():
            try:
                items = self.client.get_announcements()
            except Exception:
                return
            self._sig.announcements_ready.emit(items or [])
        threading.Thread(target=_run, daemon=True).start()
```

Move the UI text-building code into:

```python
    def _on_announcements_ready(self, items: list):
        if not items:
            return
        lines = ["公告"]
        for a in items:
            prefix = _PRIORITY_LABEL.get(a.get("priority", ""), "")
            title = a.get("title", "")
            lines.append(f"  {prefix}{title}")
            content = a.get("content", "")
            if content:
                lines.append(f"    {content}")
        self.label_qr.setText("\n".join(lines))
        self.label_qr.setTextFormat(Qt.TextFormat.PlainText)
        self.label_qr.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.label_qr.setMinimumHeight(100)
```

- [ ] **Step 4: Move usage refresh off UI thread**

In `app.py`, add a small signal QObject or use an existing pattern. The preferred minimal approach:

1. Import `QObject` and `pyqtSignal` from `PyQt6.QtCore`.
2. Add:

```python
class _MainSignals(QObject):
    usage_ready = pyqtSignal(dict)
```

3. In `MainWindow.__init__`, create:

```python
        self._sig = _MainSignals()
        self._sig.usage_ready.connect(self._on_usage_ready)
```

4. Change `_update_usage` to spawn a thread:

```python
    def _update_usage(self):
        if not self.token:
            return

        def _run():
            try:
                usage = self.client.get_usage()
            except Exception:
                return
            self._sig.usage_ready.emit(usage)

        import threading
        threading.Thread(target=_run, daemon=True).start()
```

5. Add:

```python
    def _on_usage_ready(self, usage: dict):
        self.usage_indicator.setText(f"今日 {usage['chaptersUsed']} / {usage['limit']} 次")
```

Keep existing text style if needed.

## Task 6: Fix Static Check Blockers And Python Version Metadata

**Files:**
- Modify: `client/qidian_save/desktop/app.py`
- Modify: `client/pyproject.toml`

- [ ] **Step 1: Fix undefined `QStackedWidget` annotation**

In `app.py`, remove this line entirely:

```python
        self.stack: QStackedWidget  # FluentWindow 内部 stack
```

It is unused and causes `ruff F821`. Do not import `QStackedWidget` just for an unused annotation.

- [ ] **Step 2: Fix Python version metadata**

In `client/pyproject.toml`, change:

```toml
requires-python = ">=3.9"
```

to:

```toml
requires-python = ">=3.10"
```

Reason: project code uses `str | None` and `list[dict]` style annotations that are not fully compatible with Python 3.9 syntax expectations in this codebase.

- [ ] **Step 3: Run focused ruff fatal-symbol check**

Run from repo root:

```powershell
python -m ruff check client\qidian_save --select F821
```

Expected: no `F821` errors.

Do not attempt to fix every style warning in this task. Full cleanup can be a later plan.

## Task 7: Update Ignore Rules For Generated Artifacts

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add missing generated artifact ignores**

Append these lines under the project-specific section:

```gitignore
client/dist-exe/
*.zip
```

Do not remove tracked files. Do not run `git rm` unless explicitly asked by the user.

- [ ] **Step 2: Verify status is cleaner for generated artifacts**

Run:

```powershell
git status --short --ignored
```

Expected: `client/dist-exe/` and `qidian-save-v0.1.0-win64.zip` appear ignored, not as normal untracked files.

## Final Verification Gate

Run every command below from the specified directory. Paste the exact outputs into the final report.

From `client/`:

```powershell
python -m unittest discover -s tests -v
```

Expected: all created tests pass. There must be more than 0 tests.

From `client/`:

```powershell
python -m qidian_save adb-db
```

Expected: no `NameError`. It may print that the default directory is missing or no SQLite database was found.

From `client/`:

```powershell
python -m qidian_save decrypt does-not-exist.qd --qimei36 x --user-id y --pool-b64 z
```

Expected: no `NameError`. It may raise or print `FileNotFoundError` for the missing input file.

From repo root:

```powershell
python -m ruff check client\qidian_save --select F821
```

Expected: no errors.

From repo root:

```powershell
Select-String -Path client\qidian_save\*.py,client\qidian_save\desktop\panels\*.py -Pattern "extractall|\.extract\("
```

Expected: no unsafe extraction calls remain.

From repo root:

```powershell
python -m compileall -q client\qidian_save
```

Expected: exit code 0.

## Required Final Report Format

The implementing agent must answer in this exact shape:

```markdown
## Changed Files
- file path: one-line purpose

## Verification
- `command`: exact result

## Deferred
- Any ruff warnings not fixed because they were outside this plan.

## Notes
- Any behavior intentionally left unchanged.
```

If any verification command fails, the final report must start with:

```markdown
## Blocked
```

and include the failed command and exact error output.
