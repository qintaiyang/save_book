# qidian_save

**起点中文网书籍本地保存工具 — 桌面端 + CLI**

A local backup tool for Qidian Chinese novels — Desktop GUI + CLI.

<p align="center">
  <a href="https://qm.qq.com/q/xYfDqmUUrS">
    <img src="https://img.shields.io/badge/QQ群-1035658850-blue" alt="QQ Group">
  </a>
  <img src="https://img.shields.io/badge/version-1.1.0-green" alt="Version 1.1.0">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue" alt="Python >=3.10">
</p>

---

## 📱 交流群 / Community

**QQ 群：1035658850** [点击链接加入群聊【内测】](https://qm.qq.com/q/xYfDqmUUrS)

---

## ⚠️ 免责声明 / Disclaimer

**中文：** 本工具用于备份用户在起点中文网已购买的章节内容，仅限个人合法使用。用户应自行遵守起点中文网服务条款。开发者不对用户的使用行为承担任何责任。

**English:** This tool is intended for backing up chapters you have legally purchased on Qidian. Personal use only. Users must comply with Qidian's Terms of Service. The developer assumes no responsibility for user actions.

---

## ✨ 功能 / Features

| 中文 | English |
|------|---------|
| 搜索起点书籍 | Search Qidian novels |
| 起点扫码登录（QR + Cookie 管理） | QR code login to Qidian with Cookie management |
| **客户端抓取备份**（默认）— 本地下载加密数据 → 服务端解码 | **Client-crawl backup** (default) — local fetch → server decode |
| 服务端全权备份（传统模式） | Server-crawl backup (legacy mode) |
| 多书多账号批量备份 | Multi-book & multi-account batch backup |
| .qd 解密（Android 加密章节文件） | .qd decryption (Android encrypted chapter files) |
| ADB 工具链（root 提取参数 / 扫描 / 拉取文件 / 查看数据库） | ADB toolchain (extract params / scan / pull / inspect DB) |
| API Key 管理 | API Key management |
| 用量查询 & 公告 | Daily usage & announcements |

---

## 🚀 快速开始 / Quick Start

### 桌面端 / Desktop

```bash
# 1. 安装依赖 / Install dependencies
pip install -e .

# 2. 启动桌面端 / Launch desktop
python -m qidian_save desktop
```

> Windows 用户也可双击 `start.bat` 一键启动。
> Windows users can also double-click `start.bat`.

首次启动会弹出 GitHub 登录对话框，登录后即可使用。\
On first launch, log in via GitHub to get started.

### 系统要求 / Requirements

- **Python 3.10+**
- **ADB (Android Debug Bridge)** — Bundled at `client/adb/`, no manual install
- For .qd decryption: A rooted Android device or emulator
- 网络要求：能访问 `https://autohelp.asia`（服务端）和 `https://m.qidian.com`（起点）

---

## 📖 CLI 命令 / Commands

```bash
# ── 登录 / Login ──
python -m qidian_save login                        # GitHub Device Flow 登录
python -m qidian_save login --token <jwt>          # 直接设置 Token

# ── 搜索与目录 / Search & Catalog ──
python -m qidian_save search <keyword>             # 搜索书籍
python -m qidian_save catalog <book_id>            # 查看目录
python -m qidian_save bookshelf                    # 查看起点书架（需要起点 Cookie）

# ── 备份 / Backup ──
# 模式 1（默认）— 客户端抓取：本地下载加密数据 → 服务端解码
python -m qidian_save backup <book_id>
python -m qidian_save backup <book_id> --start 1 --end 50

# 模式 2 — 服务端全权爬取（传统，需上传 Cookie）
python -m qidian_save backup <book_id> --server-crawl
python -m qidian_save backup <book_id> --cookies-ref <ref>

# ── .qd 解密 / Decrypt ──
python -m qidian_save decrypt <file.qd>            # 单文件解密（上传服务端）
python -m qidian_save decrypt <dir/>               # 目录解密（自动打包 zip 上传）
python -m qidian_save qd-config                    # 查看/设置 .qd 解密参数
python -m qidian_save qd-config --set key=value    # 设置参数

# ── ADB 操作 / ADB Operations ──
python -m qidian_save adb-extract                  # root 提取解密参数（QIMEI36/Pool/UserID）
python -m qidian_save adb-extract -s <serial>      # 指定设备
python -m qidian_save adb-scan                     # 扫描设备上的 .qd 文件
python -m qidian_save adb-scan -s <serial>
python -m qidian_save adb-pull                     # 拉取 .qd 文件到本地
python -m qidian_save adb-pull -s <serial>
python -m qidian_save adb-db                       # 查看已拉取的 SQLite 数据库

# ── 其他 / Other ──
python -m qidian_save usage                        # 查看今日用量
python -m qidian_save renew-api-key                # 重新生成 API Key
python -m qidian_save desktop                      # 启动桌面端
```

### 备份模式说明

**v1.1 新增** — 客户端抓取模式（默认）：

1. 客户端直接从起点 AJAX API (`/majax/chapter/getChapterInfo`) 下载原始加密章节数据
2. 打包为 zip 上传到服务端
3. 服务端只做解码运算（CSS 反混淆、Fock 解密、字体处理）
4. 下载解码后的 .txt / .html 文件

**优势：** 客户端用自己的 IP 爬取，**服务端不直面起点 WAF**，抗风控能力更强。

传统服务端爬取模式可通过 `--server-crawl` 启用，适用于网络受限的客户端环境。

---

## 🌐 API 集成 / API Integration

商业用户可使用 API Key 集成到自己的项目。

Commercial users can integrate via API Key:

```python
from qidian_save import QidianSaveClient

client = QidianSaveClient(
    "https://your-server.com",
    api_key="your-api-key"
)

# 查看今日用量 / Check daily usage
usage = client.get_usage()

# 获取公告 / Fetch announcements
announcements = client.get_announcements()

# 客户端抓取模式：上传原始数据 zip 解码
with open("chapters.zip", "rb") as f:
    result = client.decode_chapter_zip(task_id, f.read(), '{"ywguid":"...","ywkey":"..."}')
```

**API 文档：[https://autohelp.asia/docs/api](https://autohelp.asia/docs/api)** 📘

完整 API 端点参考 `docs/api.md`。

| 端点 | 说明 |
|------|------|
| `POST /api/auth/github/device-code` | GitHub Device Flow 第一步 |
| `POST /api/auth/github/poll-token` | GitHub Device Flow 轮询 |
| `POST /api/backup/cookies` | 上传起点 Cookie |
| `POST /api/backup/start` | 创建备份任务 |
| `GET /api/backup/{id}` | 查询进度 |
| `GET /api/backup/{id}/chapters` | 章节列表 |
| `GET /api/backup/{id}/chapters/{cid}` | 下载章节 TXT |
| `GET /api/backup/{id}/chapters/{cid}?format=html` | 下载章节 HTML |
| `GET /api/backup/{id}/chapters/{cid}/html` | 下载章节 HTML（推荐） |
| `POST /api/backup/{id}/decode-zip` | 客户端抓取模式：上传 zip 解码 |
| `DELETE /api/backup/{id}` | 删除任务 |
| `POST /api/decrypt/qd` | 单个 .qd 解密 |
| `POST /api/decrypt/qd-zip` | 批量 .qd 解密 |
| `GET /api/announcements` | 获取公告 |
| `GET /api/usage/today` | 今日用量 |
| `GET /api/auth/me` | 获取用户信息 |

---

## 🏗️ 项目架构 / Architecture

```
qidian_save/
├── client/                   # Python 包
│   ├── pyproject.toml        # 包配置（入口: qidian_save.cli:main）
│   ├── qidian-save.spec      # PyInstaller 打包配置
│   ├── run_desktop.py        # 双模式入口（无参数=桌面端，有参数=CLI）
│   ├── adb/                  # 捆绑的 ADB 二进制文件
│   ├── data/                 # Cookie 存储 / 配置 / 备份下载（gitignored）
│   └── qidian_save/          # Python 源码
│       ├── cli.py            # argparse CLI 调度
│       ├── api_client.py     # 服务端 REST API 封装
│       ├── qidian_client.py  # 直调起点 API（搜索/目录/QR 登录/抓取章节）
│       ├── adb_utils.py      # ADB 工具（扫描/拉取/root 提取/SQLite 检查）
│       ├── zip_utils.py      # 安全解压工具（路径遍历防护）
│       └── desktop/          # PyQt6-Fluent-Widgets 桌面端
│           ├── app.py        # FluentWindow + 导航
│           ├── theme.py      # iOS 设计令牌（亮/暗）
│           ├── style/        # QSS 样式表
│           ├── panels/       # 9 个功能面板
│           └── widgets/      # 阅读器组件
├── docs/
│   ├── api.md                # API 参考文档
│   └── superpowers/          # 设计文档 / 计划
├── start.bat                 # Windows 一键启动
├── start.sh                  # Linux/macOS 一键启动
└── AGENTS.md                 # 详细开发参考
```

### 三层客户端架构

| 层 | 模块 | 职责 |
|-------|--------|-------------|
| **CLI** | `cli.py` | argparse 分发，协调后端 |
| **API** | `api_client.py` | 纯 REST 封装（认证/备份/解密/用量/公告） |
| **起点** | `qidian_client.py` | 直调 m.qidian.com（搜索/目录/QR 登录/章节抓取） |
| **ADB** | `adb_utils.py` | Android Debug Bridge 工具链 |

### 桌面端面板

| 面板 | 文件 | 功能 |
|-------|------|---------|
| 登录 | `login_panel.py` | GitHub Device Flow 认证 |
| 起点登录 | `qidian_login_panel.py` | 起点扫码登录 |
| 搜索 | `search_panel.py` | 搜索书籍 |
| 书架 | `bookshelf_panel.py` | 起点书架列表 |
| 书籍详情 | `book_detail_panel.py` | 书籍信息 / 目录 / 发起备份 |
| 备份 | `backup_panel.py` | 任务进度 / 章节列表 / 下载 |
| .qd 解密 | `qd_decrypt_panel.py` | 选择设备 → 拉取 → 解密 |
| 用量 | `usage_panel.py` | 用量展示 +API Key 管理 |

---

## 🔧 环境变量 / Environment Variables

| 变量 / Variable | 说明 / Description | 默认值 / Default |
|----------------|-------------------|----------------|
| `QIDIAN_SAVE_URL` | 服务端地址 / Server URL | `https://autohelp.asia/` |
| `QIDIAN_SAVE_TOKEN` | JWT Token（自动登录 / auto-login） | — |
| `QIDIAN_SAVE_API_KEY` | API Key（商业用户 / commercial） | — |
| `ANDROID_SERIAL` | 默认 ADB 设备序列号 | — |

---

## 📦 构建 / Build

```bash
pyinstaller client/qidian-save.spec    # 输出: dist-exe/qidian-save/
```

---

## 🔍 常见问题 / Troubleshooting

| 问题 | 检查 |
|------|------|
| 备份返回「缺少 Cookie」 | 起点 Cookie 过期，重新扫码登录 |
| 所有章节显示「试读」 | 被风控，需重新登录起点 |
| ADB 检测不到设备 | `adb devices` — USB 调试开了吗？ |
| Pool 提取失败 | 先在 QDReader 里打开一章付费章节（触发 getkey API） |
| QIMEI36 未找到 | 至少启动一次 QDReader（beacon DB 需要事件） |
| root 不可用 | 模拟器有 root；真机需要 root 权限 |
| QR 登录卡住 | 重新发起扫码 |
| MSYS2 路径乱码 | `subprocess.run` 始终使用 list-form 参数 |

---

## 🔗 相关链接 / Links

- **API 文档：[https://autohelp.asia/docs/api](https://autohelp.asia/docs/api)**
- **GitHub 仓库：[https://github.com/qintaiyang/save_book](https://github.com/qintaiyang/save_book)**
- **QQ 群：[1035658850](https://qm.qq.com/q/xYfDqmUUrS)**

---

## 📄 许可证 / License

MIT License. 仅限个人合法使用。
