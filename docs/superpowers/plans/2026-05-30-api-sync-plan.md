# API 同步 & CLAUDE.md 更新 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLAUDE.md 与实际代码对齐 + 补充客户端缺失的服务端 API 适配

**Architecture:** 三步骤依序执行 — (1) 更新文档 → (2) 修改 API 客户端 → (3) 适配 CLI + 桌面端。每步无外部依赖，可独立测试。

**Tech Stack:** Python 3.9+, requests, PyQt6, PyQt6-Fluent-Widgets

---

### Task 1: 更新 CLAUDE.md（根目录 + 客户端）和记忆文件

**Files:**
- Modify: `E:\data\网站\qi_dian save\qidian_save\CLAUDE.md`
- Modify: `C:\Users\31439\.claude\projects\E--data----qi-dian-save-qidian-save\memory\client-architecture.md`

- [ ] **Step 1: 修正项目根目录 CLAUDE.md 中的文件结构**

将 panels/ 注释从 "8 个功能面板" 改为 "7 个功能面板"，在仓库树结构图中反映 `client/` 下的 `pyproject.toml` 实际位置，确认 `capture_addon.py` 已删除不出现。

文件: `E:\data\网站\qi_dian save\qidian_save\CLAUDE.md`

```diff
-│   │           ├── panels/     ─ 8 个功能面板
+│   │           ├── panels/     ─ 7 个功能面板（login_panel 仅用于 LoginDialog，非导航面板）
-│   ├── pyproject.toml
+│   └── pyproject.toml           ← 在 client/ 目录内，不是根目录（注意路径）
```

- [ ] **Step 2: CLI 框架说明 — 确认当前代码使用 argparse**

文件第 68 行 `cli.py` 说明不变，但增加 `renew-api-key` 到命令列表（第 93-115 行）。

在命令列表末尾新增 `renew-api-key`：

```diff
 python -m qidian_save desktop                # 启动 PyQt6 桌面端
+python -m qidian_save renew-api-key          # 重新生成 API Key
```

- [ ] **Step 3: 更新 API 端点表**

文件第 154-174 行，增加 `renew-api-key` 端点，修正下载端点说明：

```diff
 | GET | /api/backup/{id}/chapters/{cid} | 下载单章 TXT | ✅ |
+| POST | /api/auth/api-key/regenerate | 重新生成 API Key | ✅ |
```

并将下载端点说明统一：

```diff
-| GET | /api/backup/{id}/chapters/{cid} | 下载单章 TXT | ✅ |
+| GET | /api/backup/{id}/chapters/{cid} | 下载章节（?format=text|html） | ✅ |
```

- [ ] **Step 4: 更新记忆文件**

文件: `C:\Users\31439\.claude\projects\E--data----qi-dian-save-qidian-save\memory\client-architecture.md`

删除第 5 行 `capture_addon.py` 引用，更新面板数为 7 个导航面板。

- [ ] **Step 5: 提交 CLAUDE.md 变更**

```bash
git add CLAUDE.md
git commit -m "docs: sync CLAUDE.md with actual code structure

- Fix panels count (7 nav panels, login_panel is LoginDialog-only)
- Remove capture_addon.py references
- Add renew-api-key to CLI list
- Add /api/auth/api-key/regenerate to API endpoints table

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: API 客户端更新（api_client.py）

**Files:**
- Modify: `E:\data\网站\qi_dian save\qidian_save\client\qidian_save\api_client.py`

- [ ] **Step 1: 新增 `renew_api_key()` 方法**

在 `get_me()` 方法之后（第 92 行后）插入：

```python
    def renew_api_key(self) -> dict:
        """重新生成 API Key"""
        return self._post("/api/auth/api-key/regenerate")
```

- [ ] **Step 2: 修改 `download_chapter()` 统一用 `format` 参数**

将第 133-135 行：

```python
    def download_chapter(self, task_id: int, chapter_id: str) -> dict:
        """下载纯文本格式章节，返回 {"decodedText": "..."}"""
        return self._get(f"/api/backup/{task_id}/chapters/{chapter_id}")
```

替换为：

```python
    def download_chapter(self, task_id: int, chapter_id: str, format: str = "text") -> dict | str:
        """下载章节内容

        Args:
            format: "text" 返回 {"decodedText": "..."}
                    "html" 返回原始 HTML 字符串
        """
        resp = self.session.get(
            f"{self.base_url}/api/backup/{task_id}/chapters/{chapter_id}",
            params={"format": format},
            timeout=30,
        )
        self._raise_on_error(resp)
        if format == "html":
            return resp.text
        return resp.json()
```

- [ ] **Step 3: 删除 `download_chapter_html()` 方法**

删除第 137-148 行（整个 `download_chapter_html` 方法）。

- [ ] **Step 4: 提交 api_client.py 变更**

```bash
git add client/qidian_save/api_client.py
git commit -m "feat: sync api_client with latest server API

- Add renew_api_key() method
- Unify download_chapter() with format param (text|html)
- Remove deprecated download_chapter_html()

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: CLI 新增 renew-api-key 命令

**Files:**
- Modify: `E:\data\网站\qi_dian save\qidian_save\client\qidian_save\cli.py`

- [ ] **Step 1: 新增 `cmd_renew_api_key` 函数**

在 `cmd_usage` 函数之后（第 244 行后，或 `# ── .qd 配置` 注释之前）插入：

```python
def cmd_renew_api_key(args):
    """重新生成 API Key"""
    client = _get_client(args)
    print("正在重新生成 API Key...")
    result = client.renew_api_key()
    api_key = result.get("api_key", "未知")
    print(f"\n新的 API Key: {api_key}")
    print("请更新你的 API Key 配置。旧的 API Key 已失效。")
```

- [ ] **Step 2: 注册 `renew-api-key` 子命令**

在 `build_parser()` 函数中，在 `p_usage` 定义之后（第 476 行后）插入：

```python
    p_renew = sub.add_parser("renew-api-key", help="重新生成 API Key")
    p_renew.set_defaults(func=cmd_renew_api_key)
```

- [ ] **Step 3: 提交 cli.py 变更**

```bash
git add client/qidian_save/cli.py
git commit -m "feat: add renew-api-key CLI command

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: CLI backup 下载改用 format 参数

**Files:**
- Modify: `E:\data\网站\qi_dian save\qidian_save\client\qidian_save\cli.py`

- [ ] **Step 1: 替换 `cmd_backup` 中的 HTML 下载调用**

在 `cmd_backup()` 函数（第 103-168 行），将第 155-161 行：

```python
        has_html = ch.get("hasHtml", False)
        if has_html:
            content = client.download_chapter_html(task_id, ch["chapterId"])
            ext = ".html"
        else:
            data = client.download_chapter(task_id, ch["chapterId"])
            content = data["decodedText"]
            ext = ".txt"
```

替换为：

```python
        has_html = ch.get("hasHtml", False)
        if has_html:
            content = client.download_chapter(task_id, ch["chapterId"], format="html")
            ext = ".html"
        else:
            data = client.download_chapter(task_id, ch["chapterId"], format="text")
            content = data["decodedText"]
            ext = ".txt"
```

- [ ] **Step 2: 提交 cli.py 变更**

```bash
git add client/qidian_save/cli.py
git commit -m "refactor: use unified download_chapter with format param

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: 桌面端 backup_panel 改用 format 参数

**Files:**
- Modify: `E:\data\网站\qi_dian save\qidian_save\client\qidian_save\desktop\panels\backup_panel.py`

- [ ] **Step 1: 替换 `_download_all` 中的 HTML 下载调用**

在 `_download_all()` 方法（第 177-231 行），将第 209-217 行：

```python
                    if has_html:
                        content = self.client.download_chapter_html(
                            self.task_id, cid
                        )
                        ext = ".html"
                    else:
                        data = self.client.download_chapter(self.task_id, cid)
                        content = data["decodedText"]
                        ext = ".txt"
```

替换为：

```python
                    if has_html:
                        content = self.client.download_chapter(
                            self.task_id, cid, format="html"
                        )
                        ext = ".html"
                    else:
                        data = self.client.download_chapter(
                            self.task_id, cid, format="text"
                        )
                        content = data["decodedText"]
                        ext = ".txt"
```

- [ ] **Step 2: 提交 backup_panel.py 变更**

```bash
git add client/qidian_save/desktop/panels/backup_panel.py
git commit -m "refactor: use unified download_chapter with format param in desktop

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: 桌面端 usage_panel 新增「重新生成 API Key」按钮

**Files:**
- Modify: `E:\data\网站\qi_dian save\qidian_save\client\qidian_save\desktop\panels\usage_panel.py`

- [ ] **Step 1: 新增 import**

在文件顶部（第 2-7 行）的 import 块中，增加 `QMessageBox` 导入：

```python
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QProgressBar, QMessageBox,
)
```

- [ ] **Step 2: 在刷新按钮下方增加「重新生成 API Key」按钮**

在 `_init_ui` 方法中，`self.btn_refresh` 定义之后（第 87-91 行后），插入：

```python
        # Renew API Key button
        self.btn_renew = QPushButton("  重新生成 API Key")
        self.btn_renew.setProperty("btn-type", "danger")
        self.btn_renew.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_renew.clicked.connect(self._renew_api_key)
        cl.addWidget(self.btn_renew)
```

- [ ] **Step 3: 新增 `_renew_api_key` 回调方法**

在 `_refresh()` 方法之后（第 104-124 行后）插入：

```python
    def _renew_api_key(self):
        """重新生成 API Key（需要用户确认）"""
        reply = QMessageBox.question(
            self,
            "确认重新生成",
            "确定要重新生成 API Key？\n\n旧的 Key 将立即失效，需要更新所有使用该 Key 的地方。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self.client.renew_api_key()
            new_key = result.get("api_key", "未知")
            QMessageBox.information(
                self,
                "API Key 已重新生成",
                f"新的 API Key:\n{new_key}\n\n请妥善保管，旧的 Key 已失效。",
            )
            # 刷新用量显示
            self._refresh()
        except Exception as e:
            QMessageBox.critical(
                self,
                "重新生成失败",
                f"API Key 重新生成失败:\n{str(e)}",
            )
```

- [ ] **Step 4: 提交 usage_panel.py 变更**

```bash
git add client/qidian_save/desktop/panels/usage_panel.py
git commit -m "feat: add 'renew API key' button to usage panel

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: 验证测试

- [ ] **Step 1: CLI — 验证 `renew-api-key` 命令正常**

```bash
cd "E:\data\网站\qi_dian save\qidian_save"
python -m qidian_save renew-api-key
```

期望输出：显示新的 API Key

- [ ] **Step 2: CLI — 验证 `--help` 显示新命令**

```bash
python -m qidian_save --help
```

期望输出：`renew-api-key` 出现在子命令列表中

- [ ] **Step 3: 验证 `backup` 命令下载仍正常**

```bash
python -m qidian_save backup <book_id> --start 1 --end 2
```

期望输出：正常下载章节文件

- [ ] **Step 4: 桌面端启动验证**

```bash
python -m qidian_save desktop
```

期望：应用正常启动，用量面板有「重新生成 API Key」按钮（红色），点击弹出确认对话框

- [ ] **Step 5: 最终提交**

若所有验证通过，确认当前工作目录 clean。

```bash
git status
```
