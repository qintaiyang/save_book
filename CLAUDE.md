# CLAUDE.md — qidian_save 客户端

本文档仅覆盖 **`qidian_save/`（开源客户端）**。服务端相关请参见 `qidian_save--server/` 的 CLAUDE.md。

## 仓库结构

```
E:\data\网站\qi_dian save\     ← 父目录（非 git 仓库）
├── qidian_save/                ← 当前仓库（开源客户端）
│   ├── client/                 ─ Python 包 qidian_save
│   │   └── qidian_save/
│   │       ├── __init__.py
│   │       ├── __main__.py
│   │       ├── cli.py          ─ CLI 入口（argparse）
│   │       ├── api_client.py   ─ 服务端 API 封装（纯 requests）
│   │       ├── qidian_client.py─ 直调起点 API（搜索/目录/扫码登录）
│   │       ├── adb_utils.py    ─ ADB 工具（扫描/拉取/zip/提取参数/数据库查看）
│   │       ├── desktop/        ─ PyQt6 桌面端
│   │           ├── app.py      ─ FluentWindow 主窗口 + LoginDialog
│   │           ├── theme.py    ─ 设计系统 tokens（颜色/圆角/字体）
│   │           ├── style/      ─ QSS 主题文件
│   │           │   ├── __init__.py
│   │           │   ├── light.qss   ─ 亮色主题
│   │           │   └── dark.qss    ─ 暗色主题
│   │           ├── panels/     ─ 7 个功能面板（login_panel 仅用于 LoginDialog，非导航面板）
│   │           └── widgets/    ─ 小组件（阅读器）
│   ├── docs/
│   │   └── api.md              ─ API 文档
│   ├── pyproject.toml           ← 在 client/ 目录内，不是根目录（注意路径）
│   └── CLAUDE.md               ← 本文档
│
├── qidian_save--server/        ← 闭源服务端仓库（完全独立）
├── qidian_standalone/          ← 独立子项目
├── qd_decoder/                 ← 独立子项目
└── qidian-crawler/             ← 独立子项目
```

**⚠️ 仓库边界 — 绝对遵守：**
- `qidian_save/` 和 `qidian_save--server/` 是**完全独立的 git 仓库**，各有一套 `.git`、各自的分支和远程
- **严禁**跨仓库引用（worktree/submodule/subtree）
- 当前仓库唯一远程：`origin → https://github.com/qintaiyang/save_book`
- **本地开发只管 `qidian_save/`（客户端）**，不修改服务端代码

### 🔄 跨仓库协作 — `E:\data\网站\qi_dian save\docs\` 桥梁

客户端和服务端之间通过 **父目录的 `docs/` 目录**进行文档化协调：

1. **适配服务端前，先读文档**：当客户端需要服务端配合修改时，先查看 `E:\data\网站\qi_dian save\docs\` 下的文档，了解是否已有约定
2. **创建适配文档**：如果客户端改动需要服务端配合（如新增 API 端点、修改请求/响应格式、变更业务流程），立即在 `E:\data\网站\qi_dian save\docs\` 下创建 `.md` 文档，写明：
   - 改动内容（客户端侧做了什么）
   - 服务端需要配合什么（新增/修改的接口、参数变化、逻辑变更）
   - 优先级与时间线（可选）
3. **通知约定**：文档创建后告知用户，由用户协调服务端开发

> 因为两个仓库完全独立隔离，`docs/` 是唯一的沟通桥梁，**不要口头要求服务端配合**，必须落文档。

## 分支策略

当前分支：`client-bate`（开发），稳定分支：`client-main`。
开发在 `client-bate` 进行，完成后合并到 `client-main`。

## 客户端架构

### 设计模式

| 模块 | 职责 |
|------|------|
| `cli.py` | CLI 入口（argparse），调 api_client / qidian_client / adb_utils |
| `api_client.py` | 调 `qidian_save` 服务端 API（备份/认证/.qd解密/用量/Cookie上传） |
| `qidian_client.py` | 直调起点 API（搜索/目录/扫码登录），不经过服务端 |
| `adb_utils.py` | ADB 工具：扫描设备、拉取 .qd、打包 zip、**root 提取解密参数**、多设备支持、SQLite 查看 |

### 关键约束
- **客户端不包含任何爬取或解密算法** — 全部走服务端 API
- 起点 Cookie 桥梁：客户端 `qidian_client.py` QR 扫码登录 → 本地 `data/qidian_cookies.json` → `POST /api/backup/cookies` 上传服务端 → 服务端 CookieStore
- backup 命令自动检测本地 Cookie 并上传；桌面端 book_detail_panel 直传 `qidian_cookies` 到 `start_backup`
- .qd 解密：客户端打包 zip → 上传服务端 → 服务端解压解密压缩 → 回传
- **解密参数提取**：使用 `adb_utils.extract_params()` 从已 root 设备/模拟器直接提取 QIMEI36/Pool/UserID，**无需 mitmproxy**（原 `capture_addon.py` 已删除）
- **多设备支持**：`adb-scan`/`adb-pull`/`adb-extract` 均支持 `--device`/`-s` 指定设备序列号
- UI 更新必须通过 `pyqtSignal` 或主线程回调，不能直接跨线程操作 Qt（注意 lambda 闭包延迟绑定，用默认参数 `lambda v=val:` 捕获当前值）
- ADB 路径参数注意 MSYS2 转换问题（用 list 形式避免 Git Bash 路径转换）
- ADB root 命令 `su -c` 注意引号：`su -c "cmd"`（`su -c cmd` 会导致 cmd 被当作 user login）

### UI 设计规范
- **依赖**：`PyQt6>=6.5` + `PyQt6-Fluent-Widgets>=1.11`
- **窗口类**：`FluentWindow`（frameless + NavigationInterface），非 QMainWindow
- **登录**：`LoginDialog` 模态对话框，成功后创建 FluentWindow
- **样式**：全局 QSS（`style/light.qss` / `dark.qss`），面板**不允许**内联 setStyleSheet 设置按钮/输入框颜色
- **按钮 class 语义**：无 class=主操作蓝 / secondary=次要白边框 / success=绿 / danger=红 / ghost=文字链接
- **表格操作**：用 `cellClicked` + 蓝字 QTableWidgetItem，不用 QPushButton setCellWidget
- **主题**：`setTheme()` + `setThemeColor()` + QSS 切换，支持亮色/暗色

## CLI 命令

```bash
python -m qidian_save login                  # GitHub Device Flow 登录
python -m qidian_save login --token <jwt>    # 直接设置 Token
python -m qidian_save search <keyword>       # 搜索书籍
python -m qidian_save catalog <book_id>      # 查看目录
python -m qidian_save bookshelf              # 查看起点书架
python -m qidian_save backup <book_id>       # 备份（自动上传本地 Cookie）
python -m qidian_save backup <book_id> --cookies-ref <ref>
python -m qidian_save decrypt <file.qd>      # 单 .qd 上传服务端解密
python -m qidian_save decrypt <dir/>         # 目录 zip 上传解密
python -m qidian_save usage                  # 今日用量
python -m qidian_save qd-config              # 查看 .qd 参数
python -m qidian_save qd-config --set key=value
python -m qidian_save adb-extract            # root 提取解密参数（QIMEI36/Pool/UserID）
python -m qidian_save adb-extract -s <serial># 指定设备提取
python -m qidian_save adb-scan               # ADB 扫描 .qd 文件
python -m qidian_save adb-scan -s <serial>   # 指定设备扫描
python -m qidian_save adb-pull               # ADB 拉取 .qd 文件
python -m qidian_save adb-pull -s <serial>   # 指定设备拉取
python -m qidian_save adb-db                 # 查看拉取的 SQLite 数据库
python -m qidian_save desktop                # 启动 PyQt6 桌面端
python -m qidian_save renew-api-key          # 重新生成 API Key
```

## 桌面端架构

### UI 框架

基于 **PyQt6-Fluent-Widgets**（FluentWindow），iOS 风格设计系统：

| 文件 | 说明 |
|------|------|
| `app.py` | `FluentWindow` 主窗口 + `LoginDialog` 独立登录对话框 |
| `theme.py` | 设计系统 tokens（亮色/暗色各 20 色 + 15 个设计 token） |
| `style/light.qss` | 亮色主题 QSS（iOS 浅色系） |
| `style/dark.qss` | 暗色主题 QSS |

**设计系统**：
- 亮色：`#f5f5f7` 背景 + `#007aff` iOS 蓝 + 圆角 8-14px
- 暗色：`#1c1c1e` 背景 + `#0a84ff` 暗色蓝
- 按钮 class 体系：默认(蓝) / secondary(白边框) / success(绿) / danger(红) / ghost(透明)
- 所有按钮和输入框样式由全局 QSS 控制，面板不设内联样式

**登录流程**：LoginDialog（独立模态对话框）→ 登录成功 → FluentWindow

### panels/ — 7 个功能面板

| 面板 | 文件 | 功能 |
|------|------|------|
| 搜索 | `search_panel.py` | 搜索书籍（结果表行点击蓝字跳转详情） |
| 起点扫码 | `qidian_login_panel.py` | QR 扫码登录 ptlogin.yuewen.com |
| 书架 | `bookshelf_panel.py` | 起点书架列表（蓝字链接跳转详情） |
| 书籍详情 | `book_detail_panel.py` | 详情/目录/已购/开始备份（直传 qidian_cookies） |
| 在线备份 | `backup_panel.py` | 任务管理（进度/章节/下载） |
| .qd 解密 | `qd_decrypt_panel.py` | 小白模式：选设备→拉取→选书→选章节→一键解密 |
| 用量查询 | `usage_panel.py` | 今日用量查询 |

### widgets/
- `reader.py` — 阅读器组件

## 服务端 API 端点（客户端调用的）

| 方法 | 端点 | 说明 | 需认证 |
|------|------|------|--------|
| POST | /api/auth/github/device-code | GitHub 设备流发起 | ❌ |
| POST | /api/auth/github/poll-token | GitHub 设备流轮询 | ❌ |
| POST | /api/auth/login | GitHub OAuth 兼容 | ❌ |
| GET | /api/auth/me | 用户信息 | ✅ |
| POST | /api/backup/qr | 起点二维码 | ❌ |
| POST | /api/backup/qr/poll | 轮询扫码状态 | ❌ |
| POST | /api/backup/cookies | 上传 Cookie → cookies_ref | ✅ |
| POST | /api/backup/start | 创建备份任务 | ✅ |
| GET | /api/backup/{id} | 任务进度 | ✅ |
| GET | /api/backup/{id}/chapters | 已完成章节列表 | ✅ |
| GET | /api/backup/{id}/chapters/{cid} | 下载章节（?format=text|html） | ✅ |
| POST | /api/auth/api-key/regenerate | 重新生成 API Key | ✅ |
| DELETE | /api/backup/{id} | 清理任务 | ✅ |
| POST | /api/decrypt/qd | .qd 单文件解密 | ✅ |
| POST | /api/decrypt/qd-zip | .qd zip 批量解密 | ✅ |
| GET | /api/usage/today | 今日用量 | ✅ |
| GET | /api/announcements | 公告列表 | ✅ |
| GET | /api/health | 健康检查 | ❌ |

## Cookie 桥梁（客户端视角）

```
客户端 QR 登录 (qidian_client.get_qrcode / poll_qrcode)
  → Cookie 保存 data/qidian_cookies.json
  → POST /api/backup/cookies 上传
  → 返回 cookies_ref
  → POST /api/backup/start {cookies_ref, book_id, ...}
  → 服务端逐章爬取
```

两种传 Cookie 方式：
1. **CLI**: `cmd_backup()` 自动检测 → `upload_qidian_cookies()` → `cookies_ref` → `start_backup()`
2. **桌面端**: `book_detail_panel._start_backup()` 直接传 `qidian_cookies=load_cookies()` 到 `start_backup()`

## .qd 解密工作流（客户端视角）

```
root 设备/模拟器 → adb-extract 提取 QIMEI36/Pool/UserID（自动保存配置）
                → adb-pull 拉取 .qd 文件到本地
                → decrypt <目录> 打包 zip 上传服务端 → 下载解密结果
```

桌面端「.qd解密」面板可完成上述全部操作（输入设备号 → root提取 → 拉取书籍 → 选章节 → 一键解密）。

### adb_utils.extract_params() 提取原理

| 参数 | 来源 | 提取方式 |
|------|------|----------|
| QIMEI36 | `beacon_db` 的 Java 序列化事件中 `qimei36` 字段 | 二进制搜索 + 0x74 marker + BE length 解析 |
| userId | 外部存储目录名 `/storage/.../book/<userId>/` | `adb shell ls` |
| Pool | MMKV `pref_utils` 的 `pref_fock_key` JSON 值 | root 复制 → adb pull → 正则提取 base64 |

## Debugging Tips（客户端相关）

| 症状 | 排查 |
|------|------|
| backup 返回 "缺少 Cookie" | 先扫码登录，再重试备份 |
| QR 登录卡住 | 检查轮询日志，可能需要重新发起 |
| ADB 未检测到设备 | `adb devices` 确认 USB 调试已开启 |
| 解密提示缺少参数 | `adb-extract -s <设备号>` 直接提取，或 `qd-config --set key=value` 手动设置 |
| Pool 提取失败 | 确认在 QDReader 中打开过付费章节（Pool 需要触发 getkey API 才缓存） |
| QIMEI36 提取失败 | 确认 QDReader 至少启动过一次（beacon DB 需有事件上报） |
| root 不可用 | 真机需 root，模拟器自带 root（`adb shell su -c echo ok` 测试） |
| 多设备冲突 | 用 `-s` 指定设备，或设 `ANDROID_SERIAL` 环境变量 |
| 全部章节返回 "试读" | Cookie 过期（风控），重新扫码 |
| 服务端 QR 返回 502 | ptlogin.yuewen.com 被 GFW 阻断，服务端需要代理 |
| 空 VIP 章节内容 | 未购买该章，或 Cookie 过期 |
| MSYS2 路径转换 | ADB 命令用 list 形式传参，避免 Git Bash 转义 |
| GBK 编码乱码 | Windows 终端输出中文乱码不影响功能，设置 `PYTHONIOENCODING=utf-8` 缓解 |

## 启动方式

```bash
# 桌面端
cd qidian_save
python -m qidian_save desktop

# CLI
python -m qidian_save usage
```
