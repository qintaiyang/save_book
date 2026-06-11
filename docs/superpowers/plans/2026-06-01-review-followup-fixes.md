# Review Followup Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the follow-up review findings after the first code-quality repair pass.

**Architecture:** Keep the existing PyQt signal pattern. Move blocking API polling out of Qt timer callbacks, stop stale timers when task mode changes, replace the last worker-thread `QTimer.singleShot` handoff with a signal, and align Python package metadata.

**Tech Stack:** Python 3.10+, PyQt6, unittest, ruff.

---

## Hard Rules

- Do not edit `qidian_save--server/` or any sibling repo.
- Do not touch generated artifacts: `client/build/`, `client/dist/`, `client/dist-exe/`, `client/data/`, `client/qd_files/`, `*.zip`, `*.egg-info/`.
- Do not run broad auto-format or broad `ruff --fix` over the project.
- Do not attempt to fix the 59 full-ruff style findings in this plan.
- Do not redesign the UI or rename public classes.
- Do not change API endpoint paths or request/response field names.
- Do not add dependencies.
- Do not claim completion unless the final verification commands all ran in this turn and match the expected results.

## Review Findings To Fix

1. `BackupPanel` polls `client.get_task()` directly in a Qt `QTimer` callback, so a slow network can freeze the desktop UI.
2. Switching `BackupPanel.load_task()` from a server-crawl task to a local-crawl task leaves the old `_poll_timer` active.
3. `QDDecryptPanel._set_busy_from_thread()` still uses static `QTimer.singleShot` from worker threads.
4. `client/pyproject.toml` now requires `>=3.10` but still advertises Python 3.9 in classifiers.

## Files To Modify

- Modify `client/qidian_save/desktop/panels/backup_panel.py`
  - Add worker-thread polling signal.
  - Prevent overlapping poll requests.
  - Stop polling timer when task mode changes away from server crawl.
- Modify `client/qidian_save/desktop/panels/qd_decrypt_panel.py`
  - Add `busy_changed` signal and remove worker-thread `QTimer.singleShot` handoff.
- Modify `client/pyproject.toml`
  - Remove the Python 3.9 classifier.
- Modify `client/tests/test_backup_panel_polling.py`
  - Add tests for mode switch stopping timer and worker poll scheduling.
- Create `client/tests/test_qd_decrypt_threading.py`
  - Add regression test for `_set_busy_from_thread()` using signal emit, not `QTimer.singleShot`.
- Create `client/tests/test_pyproject_metadata.py`
  - Add metadata consistency test.

## Task 1: Make BackupPanel Polling Non-Blocking

**Files:**
- Modify: `client/qidian_save/desktop/panels/backup_panel.py`
- Modify: `client/tests/test_backup_panel_polling.py`

- [ ] **Step 1: Add tests first**

Append these tests to `client/tests/test_backup_panel_polling.py`:

```python
from unittest.mock import patch
```

Add these methods inside `BackupPanelPollingTests`:

```python
    def test_switching_to_local_task_stops_server_poll_timer(self):
        client = FakeClient()
        panel = BackupPanel(client)
        panel.load_task(123, server_crawl=True)
        self.assertTrue(panel._poll_timer.isActive())

        with patch.object(panel, "_start_local_crawl"):
            panel.load_task(456, server_crawl=False)

        self.assertFalse(panel._polling)
        self.assertFalse(panel._poll_timer.isActive())

    def test_poll_task_spawns_worker_thread_instead_of_calling_api_inline(self):
        client = FakeClient()
        panel = BackupPanel(client)
        panel.task_id = 123

        with patch("qidian_save.desktop.panels.backup_panel.threading.Thread") as thread_cls:
            panel._poll_task()

        self.assertTrue(thread_cls.called)
        self.assertEqual(client.calls, 0)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run from `client/`:

```powershell
python -m unittest tests.test_backup_panel_polling -v
```

Expected before implementation: at least one new test fails. The second test should fail because `client.get_task()` is still called inline.

- [ ] **Step 3: Add polling signals and state**

In `client/qidian_save/desktop/panels/backup_panel.py`, import `threading` is already present. Extend `_CrawlSignals` or create a new signal class. Prefer a dedicated class:

```python
class _PollSignals(QObject):
    status_ready = pyqtSignal(dict)
    error = pyqtSignal(str)
```

In `BackupPanel.__init__`, add:

```python
        self._poll_sig = _PollSignals()
        self._poll_sig.status_ready.connect(self._on_poll_status)
        self._poll_sig.error.connect(self._on_poll_error)
        self._poll_in_flight = False
```

- [ ] **Step 4: Stop stale polling whenever a new task is loaded**

At the start of `load_task()`, before assigning the new task values, add:

```python
        self._polling = False
        self._poll_timer.stop()
        self._poll_in_flight = False
```

Then keep the existing field assignments. For `server_crawl=True`, `_start_polling()` will set `_polling` back to `True`.

- [ ] **Step 5: Replace inline API call in `_poll_task()`**

Replace `_poll_task()` with:

```python
    def _poll_task(self):
        if not self.task_id or not self._polling or self._poll_in_flight:
            return

        task_id = self.task_id
        self._poll_in_flight = True

        def _run():
            try:
                status = self.client.get_task(task_id)
            except Exception as e:
                self._poll_sig.error.emit(str(e))
                return
            self._poll_sig.status_ready.emit(status)

        threading.Thread(target=_run, daemon=True).start()
```

Add handlers:

```python
    def _on_poll_status(self, status: dict):
        self._poll_in_flight = False
        self.task_info = status
        total = status["totalChapters"]
        completed = status["completedChapters"]
        failed = status["failedChapters"]

        self.label_book.setText(f"{status.get('bookName', '')} ({status.get('bookId', '')})")
        self.label_status.setText(f"状态: {status['status']}  完成: {completed}  失败: {failed}")
        self.label_progress_text.setText(f"{completed} / {total}")
        self.progress.setMaximum(total)
        self.progress.setValue(completed)

        if status["status"] in ("completed", "failed"):
            self._polling = False
            self._poll_timer.stop()

    def _on_poll_error(self, msg: str):
        self._poll_in_flight = False
        self.label_status.setText(f"查询失败: {msg}")
```

Important: Do not update UI inside `_run()`.

- [ ] **Step 6: Run focused tests**

Run from `client/`:

```powershell
python -m unittest tests.test_backup_panel_polling -v
```

Expected: all tests in that file pass.

## Task 2: Replace QDDecryptPanel Worker `QTimer.singleShot`

**Files:**
- Modify: `client/qidian_save/desktop/panels/qd_decrypt_panel.py`
- Create: `client/tests/test_qd_decrypt_threading.py`

- [ ] **Step 1: Create regression test**

Create `client/tests/test_qd_decrypt_threading.py`:

```python
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.qd_decrypt_panel import QDDecryptPanel


class QDDecryptThreadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_set_busy_from_thread_uses_signal_not_qtimer_single_shot(self):
        panel = QDDecryptPanel(client=object())
        with patch("qidian_save.desktop.panels.qd_decrypt_panel.QTimer.singleShot") as single_shot, \
             patch.object(panel._sig.busy_changed, "emit") as emit:
            panel._set_busy_from_thread(False)
        single_shot.assert_not_called()
        emit.assert_called_once_with(False)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify failure**

Run from `client/`:

```powershell
python -m unittest tests.test_qd_decrypt_threading -v
```

Expected before implementation: failure because `_DecryptSignal` has no `busy_changed`, or because `QTimer.singleShot` is called.

- [ ] **Step 3: Implement signal handoff**

In `_DecryptSignal`, add:

```python
    busy_changed = pyqtSignal(bool)
```

In `QDDecryptPanel.__init__`, connect it:

```python
        self._sig.busy_changed.connect(self._set_busy)
```

Replace `_set_busy_from_thread()` with:

```python
    def _set_busy_from_thread(self, busy: bool):
        """Safely request busy-state changes from a worker thread."""
        self._sig.busy_changed.emit(busy)
```

Do not leave `QTimer.singleShot` in `_set_busy_from_thread()`.

- [ ] **Step 4: Run focused test**

Run from `client/`:

```powershell
python -m unittest tests.test_qd_decrypt_threading -v
```

Expected: test passes.

## Task 3: Align Python Metadata

**Files:**
- Modify: `client/pyproject.toml`
- Create: `client/tests/test_pyproject_metadata.py`

- [ ] **Step 1: Create metadata test**

Create `client/tests/test_pyproject_metadata.py`:

```python
from pathlib import Path
import sys
import unittest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class PyprojectMetadataTests(unittest.TestCase):
    def test_python_classifiers_match_minimum_version(self):
        data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        self.assertEqual(project["requires-python"], ">=3.10")
        self.assertNotIn("Programming Language :: Python :: 3.9", project["classifiers"])


if __name__ == "__main__":
    unittest.main()
```

Note: This repository currently runs on Python 3.13 in local verification, so `tomllib` is available. The fallback keeps the test readable but do not add `tomli` as a dependency.

- [ ] **Step 2: Run test and verify failure**

Run from `client/`:

```powershell
python -m unittest tests.test_pyproject_metadata -v
```

Expected before implementation: failure because the Python 3.9 classifier is still present.

- [ ] **Step 3: Remove stale classifier**

In `client/pyproject.toml`, remove this exact line:

```toml
    "Programming Language :: Python :: 3.9",
```

Do not change package name, version, dependencies, or URLs.

- [ ] **Step 4: Run focused test**

Run from `client/`:

```powershell
python -m unittest tests.test_pyproject_metadata -v
```

Expected: test passes.

## Task 4: Regression Verification And Review Guard

**Files:**
- No source files should be modified in this task unless a verification command exposes a real defect from Tasks 1-3.

- [ ] **Step 1: Run all tests**

Run from `client/`:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass. There must be more than 7 tests after this plan.

- [ ] **Step 2: Run fatal-symbol check**

Run from repo root:

```powershell
python -m ruff check client\qidian_save --select F821
```

Expected: `All checks passed!`

- [ ] **Step 3: Run compile check**

Run from repo root:

```powershell
python -m compileall -q client\qidian_save
```

Expected: exit code 0 and no output.

- [ ] **Step 4: Verify no unsafe zip extraction returned**

Run from repo root:

```powershell
Select-String -Path client\qidian_save\*.py,client\qidian_save\desktop\panels\*.py -Pattern "extractall|\.extract\("
```

Expected: no matches.

- [ ] **Step 5: Verify the known timer transition manually**

Run from `client/`:

```powershell
@'
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from qidian_save.desktop.panels.backup_panel import BackupPanel

class Client:
    def get_task(self, task_id):
        return {"bookName": "B", "bookId": "1", "status": "running", "totalChapters": 10, "completedChapters": 1, "failedChapters": 0}

app = QApplication.instance() or QApplication([])
p = BackupPanel(Client())
p.load_task(1, server_crawl=True)
print("after_server", p._polling, p._poll_timer.isActive())
p._start_local_crawl = lambda: None
p.load_task(2, server_crawl=False)
print("after_local", p._polling, p._poll_timer.isActive())
p._poll_timer.stop()
'@ | python -
```

Expected:

```text
after_server True True
after_local False False
```

If `after_local` shows `True True`, the stale timer bug is not fixed.

## Required Final Report Format

The implementing agent must answer exactly like this:

```markdown
## Changed Files
- `path`: one-line purpose

## Verification
- `command`: exact result

## Deferred
- Full `ruff check client\qidian_save` style cleanup remains out of scope unless explicitly requested.

## Notes
- Any behavior intentionally left unchanged.
```

If any verification fails, the final report must begin with:

```markdown
## Blocked
```

and include the failed command plus exact output.
