# qidian_save API 文档

Base URL: `http://your-server.com`

## 认证

### GitHub Device Flow — 第一步
```
POST /api/auth/github/device-code
Response: {"device_code": "...", "user_code": "ABCD-1234",
           "verification_uri": "https://github.com/login/device",
           "expires_in": 900, "interval": 5}
```

### GitHub Device Flow — 轮询
```
POST /api/auth/github/poll-token
Body: {"device_code": "..."}
Response (success): {"status": "success", "token": "jwt...", "user": {...}}
Response (pending): {"status": "pending", "error": "..."}
Response (slow_down): {"status": "slow_down", "interval": 10}
Response (expired):  {"status": "expired", "error": "..."}
Response (denied):   {"status": "denied", "error": "..."}
```

### OAuth 登录（旧，兼容）
```
POST /api/auth/login
Body: {"provider": "github", "code": "oauth_code"}
Response: {"token": "jwt...", "user": {...}}
```

### 获取用户信息
```
GET /api/auth/me
Header: Authorization: Bearer <token>
Response: {"id": 1, "username": "...", "role": "free", "dailyLimit": 1000}
```

## 备份

### 上传 Cookie（客户端本地扫码后用）
```
POST /api/backup/cookies
Header: Authorization: Bearer <token>
Body: {"cookies": {"ywguid": "123", "ywkey": "abc", ...}}
Response: {"cookiesRef": "ref_xxx", "ywguid": "123"}
```

### 开始备份
```
POST /api/backup/start
Header: Authorization: Bearer <token>
Body: {
  "book_id": "1047720448",
  "start": 1,                  # 起始章节号（1-based），默认 1
  "end": 50,                   # 结束章节号，0=全部
  "cookies_ref": "ref_xxx",    # 方式1：使用已上传的 Cookie
  "qidian_cookies": {...}      # 方式2：直接传 Cookie dict（自动上传）
}
Response: {"taskId": 7}
```

注意：
- `start` / `end` 是 **1-based** 章节序号
- 服务端内部转换为 0-based 偏移，任务可中断恢复（从断点继续）
- 新创建的 VIP 章节（需 Fock 解密）会同时生成 `.txt` 和 `.html`

### 查询进度
```
GET /api/backup/{taskId}
Header: Authorization: Bearer <token>
Response: {
  "id": 7,
  "bookId": "1047720448",
  "bookName": "...",
  "status": "running",         # running / completed / failed / cancelled
  "totalChapters": 50,
  "completedChapters": 25,
  "failedChapters": 0,
  "error": ""                  # 失败时的错误描述
}
```

### 章节列表
```
GET /api/backup/{taskId}/chapters
Header: Authorization: Bearer <token>
Response: {
  "chapters": [
    {"chapterId": "907545099", "chapterName": "第一章", "hasHtml": true},
    {"chapterId": "907545100", "chapterName": "第二章", "hasHtml": false}
  ]
}
```

`hasHtml` 字段：
- `true` → 该章节有自包含 HTML（含内嵌 CSS + 字体），可调用 HTML 端点
- `false` → 旧任务或纯文本章节，仅 `.txt` 可用

### 下载章节（纯文本）
```
GET /api/backup/{taskId}/chapters/{chapterId}
Header: Authorization: Bearer <token>
Response: {"chapterId": "907545099", "decodedText": "第一段内容...\n\n第二段内容..."}
```

### 下载章节（HTML）
```
GET /api/backup/{taskId}/chapters/{chapterId}?format=html
Header: Authorization: Bearer <token>
Response: Content-Type: text/html
          <!DOCTYPE html><html>...（浏览器直接渲染）
```

### 下载章节 HTML（独立端点，推荐）
```
GET /api/backup/{taskId}/chapters/{chapterId}/html
Header: Authorization: Bearer <token>
Response: Content-Type: text/html
          <!DOCTYPE html><html>...（浏览器直接渲染）
```

### 上传原始章节数据解码（客户端抓取模式）

```
POST /api/backup/{taskId}/decode-zip
Header: Authorization: Bearer <token>
Content-Type: multipart/form-data

file: @chapters.zip
cookies: '{"ywguid":"...","ywkey":"..."}'
```

输入 zip 格式：每章一个 `{chapterId}.json` 文件，内容为 `get_chapter_data` 的原始返回：

```json
{
  "chapterId": "907545099",
  "chapterName": "第四百三十三章",
  "cES": 2,
  "content": "base64_encrypted_content...",
  "css": ".p1 y1{order:3}.p1 y2::after{content:'x'}...",
  "randomFont": "{\"data\":[0,1,2,...]}",
  "fkp": "base64_fkp_string..."
}
```

输出 zip 格式：每章 `{chapterId}.txt` + `{chapterId}.html` + `_errors.json`（全部成功时无 `_errors.json`）。

`cookies` 为 Form 字段（字符串），内容是 JSON 序列化的 cookies dict。需要包含 `ywguid` 和 `ywkey`（Fock 解密必需），建议同时包含 `alk`/`alkts` 以便服务端自动续期。

| HTTP 状态码 | 说明 |
|-------------|------|
| 200 | 成功，返回 application/zip |
| 400 | zip 格式错误 / 内容为空 / cookies 无效 |
| 404 | 任务不存在 |
| 413 | 文件过大（超过 100MB） |
| 429 | 今日额度不足 |

> 此端点用于**客户端抓取模式**：客户端从起点 AJAX API 下载原始加密章节数据，打包为 zip 上传，服务端只做解码运算（CSS/Fock/字体处理）。详见 `/docs/jiemi`。

客户端可在收到解码 ZIP 后执行纯本地后处理：

- 从移动端 SSR 页面获取公开试读，并通过边界重叠检测与正文去重拼接。
- 使用用户显式提供的 HTTP/SOCKS 代理列表轮换试读请求。
- 根据目录和卷信息将 `{chapterId}.txt` 合并为单文件 TXT。

这些后处理不改变本接口的输入输出格式，也不在客户端实现 CSS、字体、Fock
或 `.qd` 解密算法。所有解码运算仍由服务端完成。

HTML 内容说明：
- **带 CSS 混淆的章节**（大部分付费章节）：含 YWQD 字体修正 JS + 内嵌字体 base64（约 470KB），浏览器打开即可正确渲染
- **纯文本章节**（无混淆）：简约 HTML（system-ui 字体，约 5KB）
- 可直接在浏览器中打开链接阅读

### 删除任务
```
DELETE /api/backup/{taskId}
Header: Authorization: Bearer <token>
Response: {"status": "ok"}
```
清理任务目录和 Cookie。

## 高级备份

高级备份由服务端凭据执行。客户端不上传起点账号、Cookie、签名参数或解密材料，只调用以下公开接口。

### 创建高级备份任务
```
POST /api/v1/advanced-backup/tasks
Header: Authorization: Bearer <token>
Body: {
  "bookId": 1047720448,
  "bookName": "书名",
  "chapterIds": [880699692, 880699693],
  "chapters": [
    {"chapterId": "880699692", "chapterName": "第一章"}
  ],
  "mergeText": false,
  "timeout": 60
}
Response: {
  "taskId": 123,
  "status": "queued",
  "archiveUrl": "/api/v1/advanced-backup/tasks/123/archive"
}
```

常见错误：

| HTTP 状态码 | 说明 |
|-------------|------|
| 403 | 高级备份未开放，或当前账号/会员计划无权限 |
| 503 | 服务端高级备份凭据缺失或不可用 |
| 429 | 配额不足，或活动任务过多 |

### 查看任务列表和状态
```
GET /api/v1/advanced-backup/tasks?limit=50
Response: {"items": [{"taskId": 123, "status": "running", ...}]}

GET /api/v1/advanced-backup/tasks/{taskId}
Response: {"taskId": 123, "status": "completed", "progressDone": 2, "progressTotal": 2, ...}
```

### 下载归档
```
GET /api/v1/advanced-backup/tasks/{taskId}/archive
Response: application/zip
```

任务尚未完成或工件尚不可用时，服务端可能返回 `409`，客户端应提示用户刷新状态后重试。

## .qd 解密

### 上传单个文件解密
```
POST /api/decrypt/qd
Form: file=@chapter.qd, qimei36=xxx, userId=xxx, poolB64=xxx
Response: {"decodedText": "..."}
```

### 上传 zip 批量解密
```
POST /api/decrypt/qd-zip
Form: file=@chapters.zip, qimei36=xxx, userId=xxx, poolB64=xxx
Response: application/zip (包含解密后的 .txt 文件)
```

## 公告

### 获取活跃公告
```
GET /api/announcements
Header: Authorization: Bearer <token>
Response: {
  "announcements": [
    {"id": 1, "title": "维护通知", "content": "...", "priority": "urgent", "created_at": "2026-05-29T10:00:00"}
  ]
}
```

优先级排序: urgent > important > normal

## 用量

### 今日用量
```
GET /api/usage/today
Header: Authorization: Bearer <token>
Response: {"chaptersUsed": 50, "limit": 1000, "remaining": 950}
```

## 鉴权方式

```
JWT:    Authorization: Bearer <token>
API Key: X-API-Key: <key>
```

## 认证流程

```
GitHub Device Flow:
  客户端 → POST /api/auth/github/device-code → 返回 device_code + user_code
  用户     → 打开 github.com/login/device → 输入 user_code → 授权
  客户端 → POST /api/auth/github/poll-token (轮询) → status=success → JWT
```

## 备份工作流（客户端参考）

```
1. 客户端扫码登录起点（本地直调 m.qidian.com）
   → 得到起点 Cookie

2. 上传 Cookie 到服务端
   POST /api/backup/cookies {"cookies": {...}} → 得到 cookiesRef

3. 创建备份任务
   POST /api/backup/start {"book_id": "...", "cookies_ref": "ref_xxx"}
   → 得到 taskId（异步执行）

4. 轮询进度
   GET /api/backup/{taskId} → 直到 status=completed

5. 获取章节列表
   GET /api/backup/{taskId}/chapters → 检查 hasHtml

6. 下载内容
   纯文本: GET /api/backup/{taskId}/chapters/{chapterId}
   HTML:   GET /api/backup/{taskId}/chapters/{chapterId}?format=html
```
