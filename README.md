<p align="center">
  <img src="docs/logo.png" alt="qidian_save" width="120"/>
</p>

<h1 align="center">qidian_save</h1>

<p align="center">
  起点中文网书籍本地保存工具 — 备份你已购买的每一章<br/>
  <b>客户端开源 · 桌面端 + CLI</b>
</p>

<p align="center">
  <a href="#-功能">功能</a> ·
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-项目结构">项目结构</a> ·
  <a href="#-api-文档">API 文档</a> ·
  <a href="#-免责声明">免责声明</a>
</p>

---

## 📦 功能

| 功能 | 说明 |
|------|------|
| 搜索书籍 | 搜索起点中文网书籍信息 |
| 起点扫码登录 | 扫码登录起点账号，持久化 Cookie |
| 书籍备份 | 选择章节，下载 TXT/HTML |
| .qd 解密 | 从 Android 设备提取并解密加密章节文件 |
| ADB 工具 | 扫描/拉取 .qd 文件，root 提取解密参数 |
| 用量查询 | 查看今日 API 用量 |
| 桌面端 + CLI | PyQt6 图形界面 + 命令行双模式 |

## 🚀 快速开始

### 方式一：桌面端（推荐）

```bash
# 克隆仓库
git clone https://github.com/qintaiyang/save_book.git
cd qidian_save

# Windows 一键启动
双击 start.bat

# 或手动安装
cd client
pip install -e .
python -m qidian_save desktop
```

### 方式二：CLI 模式

```bash
cd client
pip install -e .

python -m qidian_save search 仙侠          # 搜索书籍
python -m qidian_save backup <book_id>      # 备份书籍
python -m qidian_save usage                  # 查看用量
python -m qidian_save adb-extract            # root 提取解密参数
```

首次启动会弹出 GitHub 登录对话框，登录后即可使用。

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QIDIAN_SAVE_URL` | 服务端地址 | `https://autohelp.asia/` |
| `QIDIAN_SAVE_TOKEN` | JWT Token（自动登录） | - |

## 📁 项目结构

```
qidian_save/
├── start.bat / start.sh     ← 一键启动
├── client/
│   ├── adb/                 ← 捆绑 ADB（无需手动安装）
│   ├── qidian_save/         ← Python 包
│   │   ├── cli.py           ← CLI 入口
│   │   ├── api_client.py    ← 服务端 API 封装
│   │   ├── qidian_client.py ← 起点公开 API
│   │   ├── adb_utils.py     ← ADB 工具
│   │   └── desktop/         ← PyQt6 桌面端
│   │       ├── app.py       ← 主窗口 + 登录
│   │       ├── panels/      ← 7 个功能面板
│   │       ├── style/       ← QSS 主题
│   │       └── widgets/     ← 组件
│   ├── data/                ← 运行时数据（gitignored）
│   └── README.md
├── docs/api.md              ← API 文档
└── LICENSE
```

## 🧱 架构说明

```
客户端（开源）          API 调用          服务端（闭源）
┌─────────────┐                       ┌──────────────┐
│ CLI / 桌面端 │─────── 请求 ────────→│    服务端     │
│              │                       │              │
│ 搜索/目录/扫码 │                       │    (黑盒)    │
│ ADB 工具     │                       │              │
│ Cookie 桥梁  │←────── 结果 ────────│    备份引擎   │
└─────────────┘                       └──────────────┘
```

## 📖 API 文档

服务端 API 文档：[https://autohelp.asia/docs#/](https://autohelp.asia/docs#/)

包含所有可用端点、请求格式和返回示例：
- 认证 API（GitHub Device Flow / JWT）
- 备份 API（扫码/Cookie上传/创建任务/下载章节）
- .qd 解密 API
- 用量查询 API
- 公告 API
- Admin 管理 API（商业用户）

## ⚠️ 免责声明

本工具用于帮助用户**备份自己在起点中文网已合法购买的章节内容**，仅限个人学习与存档用途。

- 用户应自行遵守起点中文网服务条款及相关法律法规
- 禁止将本工具用于侵权、盗版、商业牟利或任何非法目的
- 用户需确保备份的内容仅用于个人设备，不得二次分发
- 开发者不提供、不分享、不传播任何受版权保护的内容
- 开发者不对用户的使用行为承担任何法律责任

## 📄 开源协议

本项目采用 [MIT License](LICENSE)。

```
MIT License

Copyright (c) 2026 Qintaiyang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions...
```

---

<p align="center">
  如果觉得有用，给个 ⭐ 吧～
</p>
