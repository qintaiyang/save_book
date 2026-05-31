# qidian_save

**起点中文网书籍本地保存工具 — 桌面端 + CLI**

A local backup tool for Qidian Chinese novels — Desktop GUI + CLI.

[![QQ Group](https://img.shields.io/badge/QQ群-1035658850-blue)](https://qm.qq.com/q/xYfDqmUUrS)

---

## 交流群 / Community

📱 **QQ 群：1035658850** [点击链接加入群聊【内测】](https://qm.qq.com/q/xYfDqmUUrS)

---

## 免责声明 / Disclaimer

**中文：** 本工具用于备份用户在起点中文网已购买的章节内容，仅限个人合法使用。用户应自行遵守起点中文网服务条款。开发者不对用户的使用行为承担任何责任。

**English:** This tool is intended for backing up chapters you have legally purchased on Qidian. Personal use only. Users must comply with Qidian's Terms of Service. The developer assumes no responsibility for user actions.

---

## 功能 / Features

| 中文 | English |
|------|---------|
| 搜索书籍 | Search Qidian novels |
| 起点扫码登录 | QR code login to Qidian |
| 书籍备份（选择章节 → 服务端解码 → 下载 TXT/HTML） | Backup chapters (select → server decode → download TXT/HTML) |
| .qd 解密（Android 加密章节文件解密） | .qd decryption (Android encrypted chapter files) |
| 用量查询 | Daily usage query |

---

## 快速开始 / Quick Start

### 桌面端 / Desktop

```bash
# 1. 安装依赖 / Install dependencies
pip install -e .

# 2. 启动桌面端 / Launch desktop
python -m qidian_save desktop
```

> Windows 用户也可双击 `start.bat` 一键启动。
>
> Windows users can also double-click `start.bat`.

首次启动会弹出 GitHub 登录对话框，登录后即可使用。

On first launch, log in via GitHub to get started.

### 系统要求 / Requirements

- **Python 3.9+**
- **ADB (Android Debug Bridge)** — Bundled at `client/adb/`, no manual install
- For .qd decryption: A rooted Android device or emulator

---

## CLI 命令 / Commands

```bash
# 登录 / Login
python -m qidian_save login

# 搜索 / Search
python -m qidian_save search <keyword>

# 目录 / Catalog
python -m qidian_save catalog <book_id>

# 备份 / Backup
python -m qidian_save backup <book_id>

# .qd 解密 / Decrypt
python -m qidian_save decrypt <file.qd>
python -m qidian_save decrypt <dir/>

# ADB 操作 / ADB operations
python -m qidian_save adb-extract        # root 提取解密参数 / extract decryption params
python -m qidian_save adb-scan           # 扫描 .qd 文件 / scan .qd files
python -m qidian_save adb-pull           # 拉取 .qd 文件 / pull .qd files

# 其他 / Other
python -m qidian_save usage              # 查看用量 / check usage
python -m qidian_save qd-config          # 查看/设置配置 / view/set config
```

---

## 环境变量 / Environment Variables

| 变量 / Variable | 说明 / Description | 默认值 / Default |
|----------------|-------------------|----------------|
| `QIDIAN_SAVE_URL` | 服务端地址 / Server URL | `https://autohelp.asia/` |
| `QIDIAN_SAVE_TOKEN` | JWT Token（自动登录 / auto-login） | - |
| `QIDIAN_SAVE_API_KEY` | API Key（商业用户 / commercial） | - |

---

## API 集成 / API Integration

商业用户可使用 API Key 集成到自己的项目：

Commercial users can integrate via API Key:

```python
from qidian_save import QidianSaveClient

client = QidianSaveClient(
    "https://your-server.com",
    api_key="your-api-key"
)
usage = client.get_usage()  # 查看今日用量 / check daily usage
announcements = client.get_announcements()  # 获取公告 / fetch announcements
```

服务端 API 文档（Swagger UI）：[https://autohelp.asia/docs](https://autohelp.asia/docs)

Server API docs (Swagger UI): [https://autohelp.asia/docs](https://autohelp.asia/docs)
