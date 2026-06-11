# Decode-Zip Backup Workflow Adaptation — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `python -m qidian_save backup` 切换到客户端本地爬取 + 服务端解码的新工作流，`--server-crawl` 保留旧流程。

**Architecture:** 新增 `qidian_client.get_chapter_data()` 调 AJAX API 获取原始数据；新增 `api_client.decode_chapter_zip()` 上传 zip + cookies 到 decode-zip 端点；`cli.py` 和桌面端默认使用新流程，旧流程保留为 `--server-crawl`/复选框。

**Tech Stack:** Python 3.9+, requests, PyQt6, PyQt6-Fluent-Widgets

---

## 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `client/qidian_save/qidian_client.py` | 新增 `get_chapter_data()` + `_normalize_chapter_data()` |
| 修改 | `client/qidian_save/api_client.py` | 新增 `decode_chapter_zip()` |
| 修改 | `client/qidian_save/cli.py` | 重写 `cmd_backup()` + 新参数 |
| 修改 | `client/qidian_save/desktop/panels/book_detail_panel.py` | 加复选框 + 新流程分支 |
| 修改 | `client/qidian_save/desktop/panels/backup_panel.py` | 新增本地爬取线程 + 信号 |
| 修改 | `docs/api.md` | 加入 decode-zip 端点 |
| 不修改 | `theme.py`, `style/*.qss`, `app.py`, `search_panel.py`, `qidian_login_panel.py`, `usage_panel.py`, `qd_decrypt_panel.py`, `adb_utils.py` | 保持不变 |

---

### Task 1: `qidian_client.py` — 新增 `get_chapter_data()`

**文件:** `client/qidian_save/qidian_client.py`

在文件末尾（`save_cookies` 函数之后）追加。

- [ ] **Step 1: 新增 `get_chapter_data()` 函数**

```python
def get_chapter_data(book_id: str, chapter_id: str, cookies: dict = None) -> Optional[dict]:
    """获取单章原始加密数据（调起点移动端 AJAX API）

    返回 decode-zip 输入格式：
        {chapterId, chapterName, cES, content, css, randomFont, fkp}

    返回 None 表示未购买或网络异常。
    """
    url = "https://m.qidian.com/majax/chapter/getChapterInfo"
    params = {"bookId": book_id, "chapterId": chapter_id}
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": f"https://m.qidian.com/chapter/{book_id}/{chapter_id}/",
    }
    for attempt in range(2):
        try:
            resp = _SESSION.get(url, params=params, headers=headers,
                                cookies=cookies or {}, timeout=15)
            if resp.status_code != 200:
                log(f"get_chapter_data HTTP {resp.status_code} ({book_id}/{chapter_id})")
                return None
            data = resp.json()
            if data.get("code") != 0:
                # code=1 = 未购买
                log(f"get_chapter_data code={data.get('code')} ({book_id}/{chapter_id})")
                return None
            ci = data["data"]["chapterInfo"]
            return {
                "chapterId": chapter_id,
                "chapterName": ci.get("chapterName", ""),
                "cES": ci.get("cES", 0),
                "content": ci.get("content", ""),
                "css": ci.get("css", ""),
                "randomFont": ci.get("randomFont", ""),
                "fkp": ci.get("fkp", ""),
            }
        except requests.RequestException as e:
            log(f"get_chapter_data 异常: {e} ({book_id}/{chapter_id})")
            if attempt < 1:
                time.sleep(1)
                continue
            return None
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            log(f"get_chapter_data 解析失败: {e} ({book_id}/{chapter_id})")
            return None
    return None
```

- [ ] **Step 2: 快速验证语法**

```bash
cd client && python -c "from qidian_save.qidian_client import get_chapter_data; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add client/qidian_save/qidian_client.py
git commit -m "feat: add get_chapter_data() for AJAX chapter fetch"
```

---

### Task 2: `api_client.py` — 新增 `decode_chapter_zip()`

**文件:** `client/qidian_save/api_client.py`

在 `download_chapter()` 方法之后、`cleanup_task()` 之前插入。

- [ ] **Step 1: 新增 `decode_chapter_zip()` 方法**

```python
def decode_chapter_zip(self, task_id: int, zip_data: bytes, cookies_str: str) -> bytes:
    """上传原始章节数据 zip，服务端解码后返回结果 zip

    Args:
        task_id: 备份任务 ID
        zip_data: 打包好的 zip 二进制数据（含 {chapterId}.json）
        cookies_str: JSON 序列化的 cookies 字符串

    Returns:
        解码结果的 zip 二进制数据

    Raises:
        ApiError: HTTP 400/404/413/429
    """
    resp = self.session.post(
        f"{self.base_url}/api/backup/{task_id}/decode-zip",
        files={"file": (f"chapters_{task_id}.zip", zip_data, "application/zip")},
        data={"cookies": cookies_str},
        timeout=300,
    )
    self._raise_on_error(resp)
    return resp.content
```

注意：放在 `download_chapter` 和 `cleanup_task` 之间，保持备份相关方法相邻。

- [ ] **Step 2: 快速验证语法**

```bash
cd client && python -c "from qidian_save.api_client import QidianSaveClient; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add client/qidian_save/api_client.py
git commit -m "feat: add decode_chapter_zip() API method"
```

---

### Task 3: `cli.py` — 重写 `cmd_backup()`

**文件:** `client/qidian_save/cli.py`

- [ ] **Step 1: 修改 `build_parser()` — backup 子命令增加新参数**

找到 `p_backup = sub.add_parser("backup", ...)` 及其 add_argument 调用，新增参数：

```python
p_backup = sub.add_parser("backup", help="备份书籍（默认客户端爬取，--server-crawl 用服务端全包）")
p_backup.add_argument("book_id")
p_backup.add_argument("--start", type=int, default=1)
p_backup.add_argument("--end", type=int, default=0)
p_backup.add_argument("--output", "-o")
p_backup.add_argument("--cookies-ref", help="已上传的起点 Cookie ref")
p_backup.add_argument("--server-crawl", action="store_true",
                      help="使用旧流程：服务端全包爬取+解密")
p_backup.add_argument("--batch-size", type=int, default=50,
                      help="每批处理章节数（默认 50，仅客户端抓取模式）")
p_backup.add_argument("--delay", type=float, default=1.5,
                      help="每章请求间隔秒数（默认 1.5，仅客户端抓取模式）")
p_backup.set_defaults(func=cmd_backup)
```

- [ ] **Step 2: 重写 `cmd_backup()` — 分为新旧两个流程**

用 `--server-crawl` 分支。旧流程代码从 `cmd_backup` 提取为 `_cmd_backup_server_crawl()`，保持原逻辑不变。

**完整替换 `cmd_backup()` 函数：**

```python
def cmd_backup(args):
    """备份书籍 — 默认客户端爬取，--server-crawl 使用服务端全包"""
    if args.server_crawl:
        return _cmd_backup_server_crawl(args)
    else:
        return _cmd_backup_local_crawl(args)
```

**新增 `_cmd_backup_local_crawl()`：**

```python
def _cmd_backup_local_crawl(args):
    """新流程：客户端本地爬取原始数据 → zip → 上传服务端解码 → 下载结果"""
    client = _get_client(args)
    import io, zipfile, time, json
    from .qidian_client import get_catalog as qidian_catalog, load_cookies, set_cookie_path, get_chapter_data

    # 1. Cookie 准备（与旧流程相同逻辑）
    cookies_ref = ""
    if args.cookies_ref:
        cookies_ref = args.cookies_ref
        print(f"使用指定 cookies_ref: {cookies_ref}")
    else:
        if args.cookie_file:
            set_cookie_path(args.cookie_file)
        else:
            set_cookie_path()
        local_cookies = load_cookies()
        if local_cookies and local_cookies.get("ywguid"):
            print(f"检测到本地起点 Cookie (ywguid={local_cookies['ywguid']}), 上传到服务端...")
            try:
                result = client.upload_qidian_cookies(local_cookies)
                cookies_ref = result.get("cookiesRef", "")
                print(f"Cookie 上传成功, ref={cookies_ref}")
            except Exception as e:
                print(f"Cookie 上传失败: {e}")
                print("仍将尝试备份（可能只能下载免费章节）")
        else:
            print("未检测到起点登录 Cookie。请先扫码登录:")
            print("  方式 1: python -m qidian_save desktop")
            print("  方式 2: 直接指定 cookies-ref: --cookies-ref <ref>")

    # 2. 创建服务端任务
    try:
        task = client.start_backup(args.book_id, args.start, args.end, cookies_ref)
    except Exception as e:
        print(f"创建任务失败: {e}")
        return
    task_id = task["taskId"]
    print(f"任务已创建: {task_id}")

    # 3. 本地获取目录
    qd_cookies = load_cookies()
    if not qd_cookies.get("ywguid"):
        print("未检测到本地起点 Cookie，无法开始爬取")
        return

    print("正在获取目录...")
    cat = qidian_catalog(args.book_id, cookies=qd_cookies)
    if not cat or not cat.get("chapters"):
        print("获取目录失败，请检查 book_id 和 Cookie 有效性")
        return

    chapters = cat["chapters"]
    total = len(chapters)
    end_idx = min(args.end or total, total)
    start_idx = max(1, args.start) - 1
    target = chapters[start_idx:end_idx]
    BATCH = args.batch_size
    DELAY = args.delay

    # 4. 输出目录
    book_name = cat.get('bookName', f'book_{args.book_id}')
    output_dir = args.output or str(DATA_DIR / f"{book_name}_{args.book_id}")
    os.makedirs(output_dir, exist_ok=True)

    print(f"目标: {len(target)} 章, 每批 {BATCH} 章, 间隔 {DELAY}s")
    print(f"输出: {output_dir}")
    print()

    cookies_json = json.dumps(qd_cookies, ensure_ascii=False)
    all_ok = True

    for batch_idx in range(0, len(target), BATCH):
        batch = target[batch_idx:batch_idx + BATCH]
        batch_num = batch_idx // BATCH + 1
        total_batches = (len(target) + BATCH - 1) // BATCH
        print(f"\n── 第 {batch_num}/{total_batches} 批 ({len(batch)} 章) ──")

        # 4a. 下载原始数据
        raw_data = []
        for i, ch in enumerate(batch):
            cid = ch["chapterId"]
            cname = ch.get("chapterName", cid)
            sys.stdout.write(f"  下载 [{i+1}/{len(batch)}] {cname[:30]}... ")
            sys.stdout.flush()
            data = get_chapter_data(args.book_id, cid, qd_cookies)
            if data:
                raw_data.append(data)
                sys.stdout.write("OK\n")
            else:
                buy_status = "已购" if (not ch.get("isVip") or ch.get("isBuy")) else "未购"
                sys.stdout.write(f"SKIP ({buy_status})\n")

            if i < len(batch) - 1:
                time.sleep(DELAY)

        if not raw_data:
            print("  [!] 本批无有效数据，跳过")
            continue

        # 4b. 打包 zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for rd in raw_data:
                zf.writestr(f"{rd['chapterId']}.json",
                            json.dumps(rd, ensure_ascii=False))
        zip_bytes = zip_buf.getvalue()
        print(f"  打包: {len(raw_data)} 章, {len(zip_bytes)/1024:.0f} KB")

        # 4c. 上传解码
        print(f"  上传解码中...")
        try:
            result_zip = client.decode_chapter_zip(task_id, zip_bytes, cookies_json)
        except Exception as e:
            print(f"  [!!] 解码失败: {e}")
            all_ok = False
            continue

        # 4d. 解压保存
        error_chapters = []
        try:
            with zipfile.ZipFile(io.BytesIO(result_zip)) as zf:
                for name in zf.namelist():
                    if name == "_errors.json":
                        errors_data = json.loads(zf.read(name))
                        error_chapters = errors_data if isinstance(errors_data, list) else []
                        continue
                    target_path = os.path.join(output_dir, name)
                    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
                    zf.extract(name, output_dir)
                print(f"  保存: {len(error_chapters)} 章失败")
                for ec in error_chapters:
                    print(f"    [!!] {ec}")
        except Exception as e:
            print(f"  解压失败: {e}")
            all_ok = False

    # 5. 清理
    try:
        client.cleanup_task(task_id)
        print(f"\n任务 {task_id} 已清理")
    except Exception as e:
        print(f"\n清理失败: {e}")

    print(f"\n{'✅' if all_ok else '⚠️'} 完成! 结果保存到: {output_dir}")
```

**提取旧流程为一个独立函数保持不变：**

```python
def _cmd_backup_server_crawl(args):
    """旧流程：服务端全包爬取+解密"""
    client = _get_client(args)

    # 1. 尝试获取本地起点 Cookie 并上传
    cookies_ref = ""
    if args.cookies_ref:
        cookies_ref = args.cookies_ref
        print(f"使用指定 cookies_ref: {cookies_ref}")
    else:
        if args.cookie_file:
            set_cookie_path(args.cookie_file)
        else:
            set_cookie_path()
        local_cookies = load_cookies()
        if local_cookies and local_cookies.get("ywguid"):
            print(f"检测到本地起点 Cookie (ywguid={local_cookies['ywguid']}), 上传到服务端...")
            try:
                result = client.upload_qidian_cookies(local_cookies)
                cookies_ref = result.get("cookiesRef", "")
                print(f"Cookie 上传成功, ref={cookies_ref}")
            except Exception as e:
                print(f"Cookie 上传失败: {e}")
                print("仍将尝试备份（可能只能下载免费章节）")
        else:
            print("未检测到起点登录 Cookie。请先扫码登录:")
            print("  方式 1: python -m qidian_save desktop")
            print("  方式 2: 直接指定 cookies-ref: --cookies-ref <ref>")

    # 2. 启动备份任务
    task = client.start_backup(args.book_id, args.start, args.end, cookies_ref)
    task_id = task["taskId"]
    print(f"任务已创建: {task_id}")

    while True:
        status = client.get_task(task_id)
        print(f"  进度: {status['completedChapters']}/{status['totalChapters']} 章")
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(3)

    chapters = client.list_chapters(task_id)
    book_name = status.get('bookName', f'book_{args.book_id}')

    output_dir = args.output or str(DATA_DIR / f"{book_name}_{args.book_id}")
    os.makedirs(output_dir, exist_ok=True)

    for ch in chapters:
        safe_name = ch.get("chapterName", ch["chapterId"]).replace("/", "_")[:60]
        has_html = ch.get("hasHtml", False)
        if has_html:
            content = client.download_chapter(task_id, ch["chapterId"], format="html")
            ext = ".html"
        else:
            data = client.download_chapter(task_id, ch["chapterId"], format="text")
            content = data["decodedText"]
            ext = ".txt"
        path = os.path.join(output_dir, f"{safe_name}{ext}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  [+] {path}")

    client.cleanup_task(task_id)
    print(f"完成! 共 {len(chapters)} 章保存到 {output_dir}")
```

注意：需要在文件顶部 import 区加入 `import io, zipfile`（已有 `import sys, os, json, argparse, time` 等，只需加 `io, zipfile`）。

- [ ] **Step 3: 验证语法**

```bash
cd client && python -c "from qidian_save.cli import main; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add client/qidian_save/cli.py
git commit -m "feat: rewrite cmd_backup with client-crawl default, --server-crawl legacy"
```

---

### Task 4: `book_detail_panel.py` — 加复选框和流程分支

**文件:** `client/qidian_save/desktop/panels/book_detail_panel.py`

- [ ] **Step 1: 在底部控制区域添加 "服务器抓取" 复选框**

在 `controls` 的 `cr` layout 中，`btn_select_all` 之后添加：

```python
from PyQt6.QtWidgets import QCheckBox

# 在 _init_ui 中，cr.addWidget(self.btn_select_all) 之后添加：
self.chk_server_crawl = QCheckBox("服务器抓取")
self.chk_server_crawl.setStyleSheet("font-size: 12px; color: #6b7280;")
cr.addWidget(self.chk_server_crawl)
```

- [ ] **Step 2: 修改 `_start_backup()` 增加新流程分支**

找到 `_start_backup` 方法中的 `def _do():` 线程函数，修改为：

```python
def _start_backup(self):
    if not self.book_id:
        QMessageBox.warning(self, "提示", "请先选择一本书")
        return

    checked_rows = []
    for i in range(self.table.rowCount()):
        ci = self.table.item(i, 0)
        if ci and ci.checkState() == Qt.CheckState.Checked:
            checked_rows.append(i)

    if not checked_rows:
        QMessageBox.warning(self, "提示", "请先勾选要备份的章节")
        return

    start = checked_rows[0] + 1
    end = checked_rows[-1] + 1

    self.btn_backup.setEnabled(False)
    self.btn_backup.setText("创建任务...")

    def _do():
        try:
            qd_cookies = load_cookies()
            result = self.client.start_backup(self.book_id, start, end,
                                              qidian_cookies=qd_cookies)
            task_id = result["taskId"]
            self._sig.backup_done.emit(task_id)
        except Exception as e:
            print(f"[detail] 备份创建异常: {e}", file=sys.stderr)
            self._sig.backup_failed.emit(str(e))
        finally:
            self._sig.backup_finished.emit()

    threading.Thread(target=_do, daemon=True).start()
```

替换为：

```python
def _start_backup(self):
    if not self.book_id:
        QMessageBox.warning(self, "提示", "请先选择一本书")
        return

    checked_rows = []
    for i in range(self.table.rowCount()):
        ci = self.table.item(i, 0)
        if ci and ci.checkState() == Qt.CheckState.Checked:
            checked_rows.append(i)

    if not checked_rows:
        QMessageBox.warning(self, "提示", "请先勾选要备份的章节")
        return

    start = checked_rows[0] + 1
    end = checked_rows[-1] + 1

    self.btn_backup.setEnabled(False)
    self.btn_backup.setText("创建任务...")

    server_crawl = self.chk_server_crawl.isChecked()

    def _do():
        try:
            qd_cookies = load_cookies()
            if server_crawl:
                # 旧流程：服务端全包
                result = self.client.start_backup(self.book_id, start, end,
                                                  qidian_cookies=qd_cookies)
                task_id = result["taskId"]
            else:
                # 新流程：先创建任务，等 backup_panel 处理本地爬取
                cookies_ref = ""
                try:
                    cr = self.client.upload_qidian_cookies(qd_cookies)
                    cookies_ref = cr.get("cookiesRef", "")
                except Exception:
                    pass
                result = self.client.start_backup(self.book_id, start, end,
                                                  cookies_ref=cookies_ref)
                task_id = result["taskId"]
            self._sig.backup_done.emit(task_id)
        except Exception as e:
            print(f"[detail] 备份创建异常: {e}", file=sys.stderr)
            self._sig.backup_failed.emit(str(e))
        finally:
            self._sig.backup_finished.emit()

    threading.Thread(target=_do, daemon=True).start()
```

- [ ] **Step 3: 修改 `_on_backup_done()` 传递新流程标记**

增加 `server_crawl` 参数，让 `BackupPanel` 知道使用哪种模式：

```python
# 修改 _DetailSignal 增加 server_crawl 参数
class _DetailSignal(QObject):
    catalog_ready = pyqtSignal(dict)
    catalog_error = pyqtSignal(str)
    backup_done = pyqtSignal(int, bool)  # (task_id, is_server_crawl)
    backup_failed = pyqtSignal(str)
    backup_finished = pyqtSignal()

# 修改 emit 调用
self._sig.backup_done.emit(task_id, server_crawl)

# 修改 on_backup_started 回调签名
def __init__(self, client, on_backup_started):
    ...
    self.on_backup_started = on_backup_started  # (task_id, server_crawl, book_id, cookies)

# 修改 _on_backup_done
def _on_backup_done(self, task_id: int, server_crawl: bool):
    qd_cookies = load_cookies()
    self.on_backup_started(task_id, server_crawl, self.book_id, qd_cookies)
```

- [ ] **Step 4: Commit**

```bash
git add client/qidian_save/desktop/panels/book_detail_panel.py
git commit -m "feat: add server-crawl checkbox to book detail panel"
```

---

### Task 5: `backup_panel.py` — 新增本地爬取逻辑

**文件:** `client/qidian_save/desktop/panels/backup_panel.py`

- [ ] **Step 1: 新增信号类 `_CrawlSignals` 和 `load_task` 参数扩展**

在 `_DownloadSignals` 之后新增：

```python
class _CrawlSignals(QObject):
    """本地爬取线程 → UI 主线程的信号"""
    progress = pyqtSignal(int, int, str)  # (当前, 总数, 状态文字)
    batch_done = pyqtSignal(int, str)     # (当前批完成数, 信息)
    finished = pyqtSignal(int, int)       # (成功数, 失败数)
    error = pyqtSignal(str)
```

- [ ] **Step 2: 修改 `__init__` + `load_task` 签名**

```python
class BackupPanel(QWidget):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.task_id = 0
        self.task_info = {}
        self._polling = False
        self._server_crawl = True  # 默认旧流程
        self._book_id = ""
        self._qd_cookies = {}
        self._download_sig = _DownloadSignals()
        self._download_sig.progress.connect(self._on_dl_progress)
        self._download_sig.finished.connect(self._on_dl_finished)
        self._download_sig.error.connect(self._on_dl_error)
        self._crawl_sig = _CrawlSignals()
        self._crawl_sig.progress.connect(self._on_crawl_progress)
        self._crawl_sig.batch_done.connect(self._on_crawl_batch_done)
        self._crawl_sig.finished.connect(self._on_crawl_finished)
        self._crawl_sig.error.connect(self._on_crawl_error)
        self._init_ui()

    def load_task(self, task_id: int, server_crawl: bool = True,
                  book_id: str = "", qd_cookies: dict = None):
        self.task_id = task_id
        self._server_crawl = server_crawl
        self._book_id = book_id
        self._qd_cookies = qd_cookies or {}
        if server_crawl:
            self._start_polling()
        else:
            self._start_local_crawl()
```

- [ ] **Step 3: 新增本地爬取方法**

在 `_start_polling` 之后新增：

```python
def _start_local_crawl(self):
    """启动本地爬取线程"""
    self.label_book.setText(f"正在本地爬取... (任务 #{self.task_id})")
    self.label_status.setText("准备中...")

    def _do():
        import io, zipfile, json, time
        from ...qidian_client import get_catalog as qidian_catalog, get_chapter_data

        BATCH = 50
        DELAY = 1.5

        try:
            cat = qidian_catalog(self._book_id, cookies=self._qd_cookies)
            if not cat or not cat.get("chapters"):
                self._crawl_sig.error.emit("获取目录失败")
                return

            chapters = cat["chapters"]
            total = len(chapters)
            target = chapters  # task 已按 start/end 创建
            success = 0
            failed = 0

            cookies_json = json.dumps(self._qd_cookies, ensure_ascii=False)

            for batch_idx in range(0, len(target), BATCH):
                batch = target[batch_idx:batch_idx + BATCH]

                raw_data = []
                for i, ch in enumerate(batch):
                    cid = ch["chapterId"]
                    cname = ch.get("chapterName", cid)[:30]
                    msg = f"下载 {batch_idx + i + 1}/{len(target)}: {cname}"
                    self._crawl_sig.progress.emit(batch_idx + i, len(target), msg)
                    data = get_chapter_data(self._book_id, cid, self._qd_cookies)
                    if data:
                        raw_data.append(data)
                    if i < len(batch) - 1:
                        time.sleep(DELAY)

                if not raw_data:
                    continue

                # 打包
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for rd in raw_data:
                        zf.writestr(f"{rd['chapterId']}.json", json.dumps(rd, ensure_ascii=False))

                # 上传解码
                try:
                    result_zip = self.client.decode_chapter_zip(
                        self.task_id, zip_buf.getvalue(), cookies_json
                    )
                except Exception as e:
                    self._crawl_sig.batch_done.emit(0, f"解码失败: {e}")
                    failed += len(raw_data)
                    continue

                # 解压保存
                book_name = cat.get('bookName', f'book_{self._book_id}')
                output_dir = str(DATA_DIR / f"{book_name}_{self._book_id}")
                os.makedirs(output_dir, exist_ok=True)

                try:
                    with zipfile.ZipFile(io.BytesIO(result_zip)) as zf:
                        for name in zf.namelist():
                            if name == "_errors.json":
                                import json as _json
                                errs = _json.loads(zf.read(name))
                                failed += len(errs) if isinstance(errs, list) else 0
                                continue
                            zf.extract(name, output_dir)
                        success += sum(1 for rd in raw_data)
                except Exception:
                    failed += len(raw_data)

                self._crawl_sig.batch_done.emit(len(raw_data), f"批 {batch_idx//BATCH+1} 完成")

            self._crawl_sig.finished.emit(success, failed)

        except Exception as e:
            self._crawl_sig.error.emit(str(e))

    threading.Thread(target=_do, daemon=True).start()
```

- [ ] **Step 4: 新增信号处理槽**

```python
def _on_crawl_progress(self, current: int, total: int, msg: str):
    self.label_status.setText(msg)
    self.label_progress_text.setText(f"{current} / {total}")
    self.progress.setMaximum(total)
    self.progress.setValue(current)

def _on_crawl_batch_done(self, count: int, info: str):
    self.label_dl_progress.setText(info)

def _on_crawl_error(self, msg: str):
    self.label_status.setText(f"爬取失败: {msg}")

def _on_crawl_finished(self, success: int, failed: int):
    self._polling = False
    if failed == 0:
        self.label_status.setText(f"✅ 全部完成 ({success} 章)")
    else:
        self.label_status.setText(f"⚠️ 完成 {success} 章, {failed} 章失败")
```

- [ ] **Step 5: 修改 `app.py` 中 `_on_backup_started` 调用**

`MainWindow._on_backup_started` 中把新参数传下去：

```python
def _on_backup_started(self, task_id: int, server_crawl: bool = True,
                       book_id: str = "", qd_cookies: dict = None):
    self.current_task_id = task_id
    self.panels["backup"].load_task(task_id, server_crawl, book_id, qd_cookies)
    self.switchTo(self.panels["backup"])
```

注意：`app.py` 中 `on_backup_started = on_backup_started` 的构造函数参数是 `self.on_backup_started`。

在 `MainWindow.__init__` 中，`self.on_backup_started = on_backup_started` 已经保存了回调。所以：

```python
# 在 MainWindow.__init__ 中
self.panels["detail"] = BookDetailPanel(self.client, self._on_book_detail_backup)

# 需要将 on_backup_started 回调改为新签名
def _on_book_detail_backup(self, task_id: int, server_crawl: bool, book_id: str, qd_cookies: dict):
    self._on_backup_started(task_id, server_crawl, book_id, qd_cookies)
```

- [ ] **Step 6: Commit**

```bash
git add client/qidian_save/desktop/panels/backup_panel.py client/qidian_save/desktop/app.py
git commit -m "feat: add local crawl mode to backup panel"
```

---

### Task 6: `docs/api.md` — 更新 API 文档

**文件:** `docs/api.md`

- [ ] **Step 1: 在备份 API 章节加入 decode-zip 端点**

在 "下载章节（独立端点，推荐）" 之后、HTML 内容说明之前插入：

```markdown
### 上传原始章节数据解码

```
POST /api/backup/{taskId}/decode-zip
Header: Authorization: Bearer <token>
Content-Type: multipart/form-data

file: @chapters.zip
cookies: '{"ywguid":"...","ywkey":"..."}'
```

输入 zip：每章一个 `{chapterId}.json`，内容为 `get_chapter_data` 的原始返回（含 `chapterId`, `chapterName`, `cES`, `content`, `css`, `randomFont`, `fkp`）。

输出 zip：同目录下每章 `{chapterId}.txt` + `{chapterId}.html` + `_errors.json`（全部成功时无 `_errors.json`）。

`cookies` 为 Form 字段（字符串），内容是 JSON 序列化的 cookies dict，需要包含 `ywguid` 和 `ywkey`（Fock 解密必需），建议同时包含 `alk`/`alkts`。

| HTTP | 说明 |
|------|------|
| 200 | 成功，返回 application/zip |
| 400 | zip 格式错误/内容为空/cookies 无效 |
| 404 | 任务不存在 |
| 413 | 文件过大（超过 100MB）|
| 429 | 今日额度不足 |
```

- [ ] **Step 2: Commit**

```bash
git add docs/api.md
git commit -m "docs: add decode-zip endpoint to API docs"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 单元级验证 — 导入测试**

```bash
cd client
python -c "
from qidian_save.qidian_client import get_chapter_data, get_catalog
from qidian_save.api_client import QidianSaveClient
from qidian_save.cli import build_parser
p = build_parser()
args = p.parse_args(['backup', '1047720448'])
assert args.server_crawl == False
assert args.batch_size == 50
assert args.delay == 1.5
print('✅ CLI parse OK')

args2 = p.parse_args(['backup', '1047720448', '--server-crawl'])
assert args2.server_crawl == True
print('✅ --server-crawl flag OK')

print('✅ 全部通过')
"
```

- [ ] **Step 2: 桌面端导入测试**

```bash
cd client
python -c "
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from qidian_save.desktop.panels.book_detail_panel import BookDetailPanel
from qidian_save.desktop.panels.backup_panel import BackupPanel, _CrawlSignals
print('✅ Desktop panels import OK')
"
```

- [ ] **Step 3: Commit 最终验证**

```bash
git log --oneline -10
```

- [ ] **Step 4: 提交所有变更**

```bash
git add -A
git commit -m "feat: adapt backup workflow for decode-zip endpoint"
```

---

## 回退指南

如果新流程出现问题，用户可以：
1. CLI: 加 `--server-crawl` 参数回到旧流程
2. 桌面端: 勾选「服务器抓取」复选框回到旧流程
3. 旧流程代码完整保留在 `_cmd_backup_server_crawl()` 中，未做任何修改
