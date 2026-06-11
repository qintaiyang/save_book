# Preview, Proxy, and Chapter Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add public preview completion, user-configured rotating proxies, and catalog-ordered TXT merging while keeping every decode operation on the server.

**Architecture:** Add three focused client modules for proxy selection, preview extraction/deduplication, and chapter merging. Extend the existing local crawl coordinator and server-download postprocessing without changing the server API, then expose options through CLI and PyQt6.

**Tech Stack:** Python 3.10+, requests, concurrent.futures, PyQt6, unittest

---

### Task 1: Proxy pool

**Files:**
- Create: `client/qidian_save/proxy.py`
- Test: `client/tests/test_proxy.py`

- [ ] Write failing tests for URL parsing, round-robin rotation, and disabled direct mode.
- [ ] Run `python -m unittest client.tests.test_proxy -v` and confirm missing module failure.
- [ ] Implement a lock-protected `ProxyPool` with `requests_proxies()`.
- [ ] Run the proxy tests and confirm they pass.

### Task 2: Preview extraction and deduplication

**Files:**
- Create: `client/qidian_save/chapter_preview.py`
- Test: `client/tests/test_chapter_preview.py`

- [ ] Write failing tests for SSR extraction, HTML paragraph conversion, overlap removal, and batch fetch failure isolation.
- [ ] Run `python -m unittest client.tests.test_chapter_preview -v` and confirm missing module failure.
- [ ] Implement `extract_preview_text`, `merge_preview_text`, `fetch_preview`, and `fetch_previews`.
- [ ] Run the preview tests and confirm they pass.

### Task 3: Catalog-aware chapter merge

**Files:**
- Create: `client/qidian_save/chapter_merge.py`
- Modify: `client/qidian_save/qidian_client.py`
- Test: `client/tests/test_chapter_merge.py`

- [ ] Write failing tests for volume metadata, ordered output, TOC generation, and missing chapter placeholders.
- [ ] Run `python -m unittest client.tests.test_chapter_merge -v` and confirm missing module or metadata failure.
- [ ] Preserve volume name/code/order in `get_catalog()`.
- [ ] Implement `merge_chapters()` using `{chapterId}.txt` files.
- [ ] Run merge tests and confirm they pass.

### Task 4: Local crawl integration

**Files:**
- Modify: `client/qidian_save/local_crawl_engine.py`
- Test: `client/tests/test_local_crawl_postprocess.py`

- [ ] Write a failing integration test with a fake decode client and mocked preview batch.
- [ ] Run the test and confirm the new options are rejected.
- [ ] Start preview collection concurrently, preserve ZIP decode behavior, merge previews after extraction, then create the combined TXT.
- [ ] Run the integration test and existing ZIP tests.

### Task 5: CLI integration and regression repair

**Files:**
- Modify: `client/qidian_save/cli.py`
- Modify: `client/tests/test_cli_regressions.py`

- [ ] Add failing parser tests for `--preview`, `--merge`, repeated `--proxy`, and rotation validation.
- [ ] Add a failing regression test for the existing undefined `all_ok` completion branch.
- [ ] Pass new options into `local_crawl()` and replace `all_ok` with a result derived from `failed`.
- [ ] Run CLI regression tests.

### Task 6: PyQt6 integration

**Files:**
- Modify: `client/qidian_save/desktop/panels/book_detail_panel.py`
- Modify: `client/qidian_save/desktop/panels/backup_panel.py`
- Modify: `client/qidian_save/desktop/app.py`
- Test: `client/tests/test_desktop_backup_options.py`

- [ ] Add failing construction and option-forwarding tests.
- [ ] Add preview, merge, and proxy controls using global QSS styles.
- [ ] Forward an options dictionary through `MainWindow` into `BackupPanel`.
- [ ] Apply the same postprocessor after server-mode “download all”.
- [ ] Run desktop construction and polling tests offscreen.

### Task 7: Boundary and full verification

**Files:**
- Modify: `docs/api.md`
- Test: `client/tests/test_no_client_decode_algorithms.py`

- [ ] Document that preview/proxy/merge are client postprocessing and decode remains server-side.
- [ ] Add a focused boundary test ensuring the new modules do not import local decode/decrypt modules.
- [ ] Run `python -m unittest discover -s client/tests -v`.
- [ ] Run `python -m compileall client/qidian_save`.
- [ ] Run `git diff --check`.
- [ ] Review `git diff` for credentials, accidental server changes, and unrelated reversions.
