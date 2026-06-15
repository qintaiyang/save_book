# 点备客户端

**起点中文网书籍备份工具，支持在线备份、本地备份、书籍搜索和书架读取。**

![点备项目图](../docs/assets/dianbei-app.png)

[![QQ Group](https://img.shields.io/badge/QQ群-1035658850-blue)](https://qm.qq.com/q/xYfDqmUUrS)

## 交流群

QQ 群：1035658850
链接：[加入群聊](https://qm.qq.com/q/xYfDqmUUrS)

## 免责声明

点备用于备份用户在起点中文网已购买或有权阅读的章节内容，仅限个人学习、研究和合法备份使用。用户应自行遵守起点中文网服务条款以及所在地法律法规。开发者不对用户的使用行为承担责任。

## 客户端定位

本仓库中的客户端是开源实现，负责用户界面、登录引导、搜索、书架展示、任务提交、ADB 拉取和结果下载。签名、解码、逆向相关实现不放在客户端仓库中。

服务端提供开放 API，第三方客户端可以按接口规范自行接入。

## 主要功能

| 功能 | 说明 |
|------|------|
| 起点登录 | 支持账号密码、短信验证码等登录流程；登录状态有效期内重启客户端无需重新登录 |
| 搜索书籍 | 按关键词搜索书籍，查看书籍详情和目录 |
| 书架读取 | 使用当前起点登录会话读取书架 |
| 在线备份 | 在客户端选择书籍和章节，由服务端完成在线备份，客户端下载结果 |
| 本地备份 | 从 Android 设备拉取本地缓存章节，上传到服务端处理后保存为可阅读文本 |
| 用量查询 | 查看当前账号的每日使用额度 |
| 调试模式 | 通过 `--debug` 显示慢速备份、网页 Cookie 登录等高级调试入口 |

## 安装与启动

在仓库根目录：

```bash
pip install -e client
python run_desktop.py
```

或进入客户端目录：

```bash
cd client
pip install -e .
python -m qidian_save desktop
```

调试模式：

```bash
python -m qidian_save desktop --debug
```

## 系统要求

- Python 3.10+
- Windows、macOS 或 Linux
- 本地备份需要 Android 设备开启 USB 调试
- ADB 已随客户端附带，通常不需要手动安装

## 推荐流程

1. 打开点备客户端。
2. 在“登录”页面登录点备账号和起点账号。
3. 在“搜索书籍”或“书架”页面选择书籍。
4. 使用“在线备份”创建任务并下载结果。
5. 如需备份手机本地缓存，连接 Android 设备后使用“本地备份”。

## CLI

桌面版是推荐入口，CLI 主要用于自动化和调试。

```bash
# 登录点备账号
python -m qidian_save login

# 启动桌面版
python -m qidian_save desktop
python -m qidian_save desktop --debug

# 搜索与目录
python -m qidian_save search <keyword>
python -m qidian_save catalog <book_id>

# 在线备份
python -m qidian_save backup <book_id>
python -m qidian_save backup <book_id> --start 1 --end 20
python -m qidian_save backup <book_id> --merge

# ADB 本地备份辅助
python -m qidian_save adb-scan
python -m qidian_save adb-pull
python -m qidian_save adb-extract

# 用量
python -m qidian_save usage
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QIDIAN_SAVE_URL` | 点备服务端地址 | `https://autohelp.asia/` |
| `QIDIAN_SAVE_TOKEN` | 点备账号 JWT，用于自动登录 | 空 |

## 隐私与安全边界

- 客户端仓库开源，不包含签名、解码、逆向算法。
- 客户端不会保存起点账号密码、起点 Cookie 或 `ywkey`。
- 客户端只会在本地缓存服务端登录会话 ID、阶段和过期时间。
- 服务端负责保存和处理必要的敏感会话信息。

## License

MIT
