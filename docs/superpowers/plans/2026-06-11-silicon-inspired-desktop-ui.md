# Silicon-Inspired Desktop UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a cohesive SiliconUI-inspired dark redesign for the complete PyQt6 desktop client without changing its business behavior.

**Architecture:** Keep `FluentWindow`, existing panels, callbacks, and API clients. Add a small shared presentation layer built from standard Qt widgets and semantic dynamic properties, then centralize all visual states in `theme.py` and `dark.qss`.

**Tech Stack:** Python 3.10+, PyQt6, PyQt6-Fluent-Widgets, Qt Style Sheets, pytest

---

### Task 1: Theme Contract and Shared Components

**Files:**
- Create: `client/tests/test_desktop_theme.py`
- Create: `client/qidian_save/desktop/components.py`
- Modify: `client/qidian_save/desktop/theme.py`
- Modify: `client/qidian_save/desktop/style/dark.qss`

- [ ] **Step 1: Write failing tests for the semantic theme contract**

```python
from qidian_save.desktop.components import PageHeader, StatCard, SurfaceCard
from qidian_save.desktop.theme import DARK_TOKENS, DESIGN_TOKENS, load_qss


def test_dark_theme_exposes_required_semantic_tokens():
    required = {
        "bg_canvas", "bg_navigation", "surface_raised", "surface_inset",
        "border_subtle", "accent", "accent_highlight", "text_primary",
        "text_secondary", "success", "warning", "danger",
    }
    assert required <= DARK_TOKENS.keys()
    assert DESIGN_TOKENS["control_height"] == 38


def test_shared_components_publish_qss_properties(qtbot):
    header = PageHeader("Search", "Find books", "LIBRARY")
    card = SurfaceCard()
    stat = StatCard("Used", "--", "accent")
    qtbot.addWidget(header)
    qtbot.addWidget(card)
    qtbot.addWidget(stat)
    assert header.property("ui-role") == "page-header"
    assert card.property("ui-role") == "surface-card"
    assert stat.property("accent") == "accent"


def test_dark_qss_styles_core_semantic_roles():
    qss = load_qss()
    for selector in (
        '[ui-role="page-header"]',
        '[ui-role="surface-card"]',
        '[ui-role="stat-card"]',
        '[ui-role="empty-state"]',
    ):
        assert selector in qss
```

- [ ] **Step 2: Run the focused test and confirm it fails because the new module and tokens do not exist**

Run: `python -m pytest tests/test_desktop_theme.py -q`

Expected: collection failure for `qidian_save.desktop.components`.

- [ ] **Step 3: Implement semantic tokens and shared components**

Create `PageHeader`, `SurfaceCard`, `StatCard`, `EmptyState`, and `configure_page_layout`.
Each class uses object names or `ui-role`/`accent` dynamic properties, standard Qt
layouts, and no color-specific inline style sheets.

- [ ] **Step 4: Replace `dark.qss` with complete application-level styling**

Cover canvas, navigation, title bar, cards, headings, labels, buttons, inputs,
combo boxes, check boxes, progress bars, tables, trees, text editors, tabs,
scrollbars, dialogs, tooltips, and all semantic shared-component roles.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_desktop_theme.py -q`

Expected: all tests pass.

### Task 2: Main Shell and Login

**Files:**
- Create: `client/tests/test_desktop_shell.py`
- Modify: `client/qidian_save/desktop/app.py`
- Modify: `client/qidian_save/desktop/panels/login_panel.py`

- [ ] **Step 1: Write failing shell construction tests**

Use a minimal fake API client and `QT_QPA_PLATFORM=offscreen`. Verify:

- `LoginDialog` has the `login-dialog` role.
- `MainWindow` starts in dark theme.
- Every navigation panel is registered.
- The status control has the `navigation-status` role.
- Main window minimum size is at least 1024 by 680.

- [ ] **Step 2: Run tests and confirm expected property and geometry failures**

Run: `python -m pytest tests/test_desktop_shell.py -q`

- [ ] **Step 3: Implement the shell redesign**

Apply the dark theme once at application startup, add stable semantic roles,
configure compact navigation width and selection behavior through supported Fluent
APIs, improve the status widget hierarchy, and give the login dialog a centered
branded surface.

- [ ] **Step 4: Run shell and theme tests**

Run: `python -m pytest tests/test_desktop_shell.py tests/test_desktop_theme.py -q`

Expected: all tests pass.

### Task 3: Search, QR Login, Bookshelf, and Book Detail

**Files:**
- Create: `client/tests/test_desktop_panels.py`
- Modify: `client/qidian_save/desktop/panels/search_panel.py`
- Modify: `client/qidian_save/desktop/panels/qidian_login_panel.py`
- Modify: `client/qidian_save/desktop/panels/bookshelf_panel.py`
- Modify: `client/qidian_save/desktop/panels/book_detail_panel.py`

- [ ] **Step 1: Write failing presentation tests**

Construct each panel with fake clients and assert:

- Each panel has one `PageHeader`.
- Major sections use `SurfaceCard`.
- Standard controls have no color-bearing inline style sheet.
- Primary actions use `btn-type="primary"` and secondary actions use
  `btn-type="secondary"`.
- Empty/status labels use semantic `ui-role` values.

- [ ] **Step 2: Run tests and confirm failures against the current panel structure**

Run: `python -m pytest tests/test_desktop_panels.py -q`

- [ ] **Step 3: Rebuild the four panel layouts**

Use shared page margins, headers, cards, compact toolbars, consistent tables, and
semantic statuses. Keep every signal, callback, thread, and API call unchanged.
Replace hardcoded blue action text with the shared accent token through a semantic
table-item helper.

- [ ] **Step 4: Run panel tests and existing regressions**

Run: `python -m pytest tests/test_desktop_panels.py tests/test_cli_regressions.py -q`

Expected: all tests pass.

### Task 4: Backup, Decryption, Usage, and Reader

**Files:**
- Modify: `client/tests/test_desktop_panels.py`
- Modify: `client/tests/test_backup_panel_polling.py`
- Modify: `client/tests/test_qd_decrypt_threading.py`
- Modify: `client/qidian_save/desktop/panels/backup_panel.py`
- Modify: `client/qidian_save/desktop/panels/qd_decrypt_panel.py`
- Modify: `client/qidian_save/desktop/panels/usage_panel.py`
- Modify: `client/qidian_save/desktop/widgets/reader.py`

- [ ] **Step 1: Extend failing tests for workflow-heavy panels**

Assert semantic section roles, action hierarchy, inset technical log surfaces,
usage stat cards, and reader content roles. Preserve existing polling and
main-thread signal expectations.

- [ ] **Step 2: Run focused tests and confirm presentation failures while existing behavioral tests stay meaningful**

Run: `python -m pytest tests/test_desktop_panels.py tests/test_backup_panel_polling.py tests/test_qd_decrypt_threading.py -q`

- [ ] **Step 3: Reorganize backup and decryption presentation**

Keep behavior intact while grouping summary, progress, chapter data, parameters,
actions, and logs into explicit surfaces. Remove inline light colors, emoji used as
structural icons, and duplicated button styles.

- [ ] **Step 4: Rebuild usage and reader presentation**

Use `StatCard` for metrics, a semantic progress surface, low-glare reading content,
and consistent reader chrome.

- [ ] **Step 5: Run focused and complete tests**

Run: `python -m pytest tests/test_desktop_panels.py tests/test_backup_panel_polling.py tests/test_qd_decrypt_threading.py -q`

Expected: all tests pass.

### Task 5: Static Audit, Runtime Verification, and Visual QA

**Files:**
- Create: `client/tests/test_desktop_style_audit.py`
- Modify: UI files only when the audit exposes violations

- [ ] **Step 1: Write an audit test for forbidden visual drift**

Scan desktop Python files and fail on panel-level color declarations in
`setStyleSheet`, known light-theme colors, and structural emoji in button text.
Allow documented dynamic exceptions only.

- [ ] **Step 2: Run the audit and remove all reported violations**

Run: `python -m pytest tests/test_desktop_style_audit.py -q`

- [ ] **Step 3: Run formatting-neutral static checks**

Run: `python -m compileall qidian_save`

Run: `git diff --check`

Expected: exit code 0.

- [ ] **Step 4: Run the complete test suite**

Run: `python -m pytest tests -q`

Expected: zero failures.

- [ ] **Step 5: Render representative windows offscreen**

Create a temporary verification script outside the repository that constructs the
login dialog, main window, search, decryption, and usage views with fake data,
captures PNGs with `QWidget.grab()`, and exits without entering a persistent event
loop.

- [ ] **Step 6: Inspect screenshots with the configured vision tool**

Check spacing, clipping, contrast, selected navigation state, card hierarchy,
table density, disabled states, and remaining light surfaces. Fix any defect and
repeat Steps 3-6.

- [ ] **Step 7: Review the final diff against the approved specification**

Confirm all nine UI surfaces are covered, business logic is unchanged, no server
files were touched, and user-owned unrelated changes remain intact.
