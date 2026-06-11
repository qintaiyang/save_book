# qidian_save 客户端备份工作流适配

**日期:** 2026-05-31
**状态:** 已定稿

## 背景

服务端新增 `POST /api/backup/{task_id}/decode-zip` 端点。客户端可以从本地调用 Qidian AJAX API 获取原始加密章节数据，打包为 zip 上传到服务端进行解码，下载解码结果。此工作流将服务端从 Qidian WAF 风险中解放出来——客户端用自己的 IP 爬取原始数据，服务端只做解密运算。

## 变更总览

| 文件 | 变更 |
|------|------|
| `qidian_client.py` | 新增 `get_chapter_data()` — 调 AJAX API 获取单章原始加密数据 |
| `api_client.py` | 新增 `decode_chapter_zip()` — 上传原始数据 zip + cookies 并下载解码结果 |
| `cli.py` | 重写 `cmd_backup()` — 默认使用客户端抓取工作流；`--server-crawl` 保留旧流程 |
| `desktop/panels/book_detail_panel.py` | 更新备份启动逻辑，对齐 CLI 新流程 |
| `desktop/panels/backup_panel.py` | 更新进度显示和下载逻辑，对齐新流程 |
| `docs/api.md` | 加入 `POST /api/backup/{task_id}/decode-zip` 端点文档 |

## 详细设计

### 1. `qidian_client.py` — 新增 `get_chapter_data()`

```python
def get_chapter_data(book_id: str, chapter_id: str, cookies: dict) -> Optional[dict]:
    """获取单章原始加密数据（调起点移动端 AJAX API）

    返回格式直接对接到 decode-zip 输入要求：
        {chapterId, chapterName, cES, content, css, randomFont, fkp}

    返回 None 表示该章未购买或网络异常。code=1 = 未购买章节。
    """
```

**实现要点：**
- 调用 `GET /majax/chapter/getChapterInfo?bookId={bookId}&chapterId={chapterId}`
- 使用 `_mobile_headers` + `Accept: application/json` + `Referer: https://m.qidian.com/chapter/{bookId}/{chapterId}/`
- 解析 `resp.json()` → `data.chapterInfo`，映射字段
- 复用 `qidian_client.py` 已有的 `_mobile_get()` 和 `log()` 工具函数
- 发生 `requests.RequestException` 时返回 None，不抛异常（批处理中稳健）

**复用/修改：**
- 现有的 `_mobile_get()` 签名已支持 `headers` 参数（已确认可以传入自定义 headers）
- 现有的 `get_catalog()` 已有类似逻辑，但返回格式不同，不修改它

### 2. `api_client.py` — 新增 `decode_chapter_zip()`

```python
def decode_chapter_zip(self, task_id: int, zip_data: bytes, cookies_str: str) -> bytes:
    """上传原始章节数据 zip，服务端解码后返回结果 zip

    Args:
        task_id: 备份任务 ID
        zip_data: 打包好的 zip 二进制数据（含 {chapterId}.json）
        cookies_str: JSON 序列化的 cookies 字符串

    Returns:
        解码结果的 zip 二进制数据（含 {chapterId}.txt + {chapterId}.html + 可选 _errors.json）

    Raises:
        ApiError: HTTP 400 (zip 格式无效), 404 (任务不存在), 413 (文件过大), 429 (额度不足)
        requests.RequestException: 网络错误
    """
```

**实现要点：**
- `POST /api/backup/{task_id}/decode-zip`，`Content-Type: multipart/form-data`
- `file` 字段：从 `zip_data: bytes` 构造 `io.BytesIO` 传入
- `cookies` 字段：纯文本 Form 字段（非 JSON body），内容已为 JSON 字符串
- 超时 300 秒（zip 上传 + 服务端解码可能较慢）
- 返回原始 `resp.content`（zip 二进制）

### 3. `cli.py` — 重写 `cmd_backup()`

```
用法:
  python -m qidian_save backup <book_id> [--start N] [--end N]
                                         [--batch-size N] [--delay SEC]
                                         [--server-crawl]
                                         [--cookies-ref REF]
                                         [--output PATH]

参数:
  book_id         必需。起点书籍 ID
  --start N       起始章节号（1-based，默认 1）
  --end N         结束章节号（0=全部，默认 0）
  --batch-size N  每批多少章（默认 50）
  --delay SEC     每章间隔秒数（默认 1.5）
  --server-crawl  使用旧流程：服务端全包爬取+解码
  --cookies-ref   Cookie ref（默认自动检测本地 Cookie）
  --output        保存目录
```

**新流程（默认）：**

```
1. 上传/检测本地 Cookie → cookies_ref
2. POST /api/backup/start → taskId
3. 本地调用 qidian_catalog() 获取目录和章节列表
4. 截取 [start-1:end] 范围
5. 每批 N 章：
   a. 循环 get_chapter_data() 下载原始数据，每章间隔 delay 秒
   b. 内存中打包为 {chapterId}.json 的 zip（io.BytesIO）
   c. POST decode-chapter-zip 上传解码
   d. 解压结果 zip，保存 .txt + .html 到输出目录
   e. 打印进度
6. DELETE /api/backup/{taskId} 清理
```

**旧流程（`--server-crawl`）：**
保留当前 `cmd_backup()` 代码不变：上传 Cookie → start_backup → 轮询 → 下载各章 → 清理。

**退出策略：**
- 如果任意一批 decode-zip 返回 429（额度不足），打印提示后退出，不删除任务（重试可继续）
- 如果服务器返回 400/404，打印错误后删除任务
- Ctrl+C 中断时打印当前进度，不自动清理任务（用户可以手动 DELETE）

### 4. 桌面端适配

#### `book_detail_panel.py`

在 `_start_backup()` 方法中：

```python
def _start_backup(self):
    # ... 现有参数收集 ...
    
    if self.server_crawl_mode:  # 勾选"服务器抓取"时
        # 旧流程：直传 qidian_cookies → start_backup → 轮询
        ...
    else:
        # 新流程：创建任务 → 发射信号让 backup_panel 处理本地抓取
        task = self.client.start_backup(book_id, start, end, cookies_ref)
        task_id = task["taskId"]
        self.backup_started.emit(task_id, book_id, cookies)
```

在 `book_detail_panel.py` 添加一个复选框 "服务器抓取"（默认不勾选），用于切换到旧流程。

#### `backup_panel.py`

新增方法 `start_local_crawl(task_id, book_id, cookies, start, end, batch_size, delay)`：

```python
class BackupPanel:
    def start_local_crawl(self, task_id, book_id, cookies, start, end, batch_size=50, delay=1.5):
        """在新线程中执行客户端抓取工作流"""
        self._crawl_thread = threading.Thread(
            target=self._do_local_crawl,
            args=(task_id, book_id, cookies, start, end, batch_size, delay),
            daemon=True,
        )
        self._crawl_thread.start()
    
    def _do_local_crawl(self, task_id, book_id, cookies, start, end, batch_size, delay):
        """后台线程：本地抓取 → 打包 → decode-zip → 保存"""
        ...
        # 通过 pyqtSignal 更新 UI
        self.progress_updated.emit(completed, total)
```

**UI 信号：**
- `progress_updated(completed, total)` — 更新进度条
- `chapter_decoded(chapter_id, title)` — 添加到已完成列表
- `crawl_finished(success, message)` — 备份完成/失败

### 5. `docs/api.md` 更新

加入 decode-zip 端点文档：

```markdown
### 上传原始章节数据解码

```
POST /api/backup/{taskId}/decode-zip
Content-Type: multipart/form-data
Authorization: Bearer <token>

file: @chapters.zip
cookies: '{"ywguid":"...","ywkey":"..."}'
```

输入 zip：每章 `{chapterId}.json`，内容为 get_chapter_data 原始返回
输出 zip：每章 `{chapterId}.txt` + `{chapterId}.html` + `_errors.json`
```

## 不变的部分

- `qidian_client.py` 现有函数（`search_books`, `get_catalog`, `get_bookshelf`, 扫码登录, Cookie 管理）**不变**
- `api_client.py` 现有端点封装 **不变**
- `adb_utils.py` **不变**
- `theme.py`, `style/*.qss`, `app.py` **不变**
- `qd_decrypt_panel.py`, `search_panel.py`, `qidian_login_panel.py`, `usage_panel.py` **不变**
- 服务端 `/api/backup/cookies`, `/api/decrypt/qd`, `/api/decrypt/qd-zip` 等端点调用 **不变**

## 已解决的问题

### zip 打包策略
- 默认使用内存打包 (`io.BytesIO`)，适合每批 ≤50 章的场景
- CLI 每批 50 章，平均每章 JSON ~20KB → 每批 zip ~1MB，内存模式安全
- 桌面端保留相同批次大小，不需要磁盘暂存

### `_errors.json` 处理
- 解码成功 → 直接保存 `.txt` 和 `.html`
- 解码失败（在 `_errors.json` 中）→ 打印警告，不中断后续批次
- 任务结束时汇总错误章节数，提示用户可重试

### 桌面端 UI
- ProgressBar 显示当前批次进度（已完成 N/M 章）
- 日志区域输出每章抓取状态（类似 QIDIAN_DEBUG 模式）
- 结束时弹出完成对话框，含成功/失败计数
