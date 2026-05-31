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
