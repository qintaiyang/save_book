# qidian_save

起点中文网书籍本地保存工具 — 桌面端 + CLI。

## 免责声明

本工具用于备份用户在起点中文网已购买的章节内容，仅限个人合法使用。
用户应自行遵守起点中文网服务条款。
开发者不对用户的使用行为承担任何责任。

## 快速开始（桌面端）

```bash
# 1. 安装依赖
pip install -e .

# 2. 启动桌面端
python -m qidian_save desktop
```

Windows 用户也可直接双击 `start.bat` 一键启动。

首次启动会弹出 GitHub 登录对话框，登录后即可使用。

## 功能

| 功能 | 说明 |
|------|------|
| 搜索书籍 | 搜索起点中文网书籍 |
| 起点扫码登录 | 扫码登录起点账号 |
| 书籍备份 | 选择章节 → 服务端解码 → 下载 TXT/HTML |
| .qd 解密 | 从 Android 设备提取加密章节文件 → 上传服务端解密 |
| 用量查询 | 查看今日 API 用量 |

## 系统要求

- **Python 3.9+**
- **Android 调试桥（ADB）** — 已捆绑在 `client/adb/` 目录，无需手动安装
- 如需 .qd 解密功能：需要一台已 root 的 Android 设备或模拟器

## CLI 命令

```bash
# 登录
python -m qidian_save login

# 搜索
python -m qidian_save search <关键词>

# 查看目录
python -m qidian_save catalog <book_id>

# 备份书籍
python -m qidian_save backup <book_id>

# .qd 解密
python -m qidian_save decrypt <文件.qd>
python -m qidian_save decrypt <目录/>

# ADB 操作
python -m qidian_save adb-extract        # root 提取解密参数
python -m qidian_save adb-scan           # 扫描 .qd 文件
python -m qidian_save adb-pull           # 拉取 .qd 文件

# 其他
python -m qidian_save usage              # 查看今日用量
python -m qidian_save qd-config          # 查看/设置配置
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QIDIAN_SAVE_URL` | 服务端地址 | `https://autohelp.asia/` |
| `QIDIAN_SAVE_TOKEN` | JWT Token（自动登录） | - |
| `QIDIAN_SAVE_API_KEY` | API Key（商业用户） | - |

## API 集成

商业用户可使用 API Key 集成到自己项目:

```python
from qidian_save import QidianSaveClient

client = QidianSaveClient(
    "https://your-server.com",
    api_key="your-api-key"
)
books = client.search_books("玄幻")
```

详细 API 文档见 [docs/api.md](docs/api.md)。
