# 服务端 API 同步 & CLAUDE.md 更新设计

**日期**: 2026-05-30
**状态**: 已批准

## 目标

1. 对齐 CLAUDE.md 与实际代码结构（`capture_addon.py` 已删、文件路径修正等）
2. 补充客户端缺失的服务端 API 适配（`renew-api-key`、`format` 参数）
3. 记忆同步

## 涉及文件

| 优先级 | 文件 | 改动类型 |
|--------|------|----------|
| P0 | `CLAUDE.md`（项目根目录 + 客户端）| 更新文件结构、命令列表 |
| P0 | `api_client.py` | 新增 `renew_api_key()`、修改 `download_chapter()` |
| P0 | `cli.py` | 新增 `cmd_renew_api_key`、适配 download |
| P0 | `usage_panel.py` | 新增「重新生成 API Key」按钮 |
| P1 | `backup_panel.py` | 改用 `format` 参数下载 HTML |
| P1 | 记忆文件 | 更新结构描述 |

## Step 1：更新 CLAUDE.md

### 需要修正的点

1. **文件结构** — 删除 `capture_addon.py` / `_capture_runner.py` 引用；修正 `pyproject.toml` 路径在 `client/` 下
2. **CLI 框架说明** — `cli.py` 使用的是 `argparse`（非 Click），entry_point 名 `qidian-save`
3. **桌面端面板** — 明确 7 个导航面板 + `login_panel.py` 仅 LoginDialog 使用（非导航面板）
4. **cli.py 命令列表** — 当前 13 个子命令，增加 `renew-api-key`
5. **docs/api.md**（可选）— 如果该文档与 OpenAPI 有冲突，同步更新

### 不变的内容
- 仓库边界策略（`qidian_save` ↔ `qidian_save--server` 独立）
- 分支策略（`client-bate` 开发 → `client-main` 稳定）
- 跨仓库协作规则（通过 `docs/` 桥梁）
- Cookie 桥梁设计
- .qd 解密工作流
- Debugging Tips

## Step 2：API 客户端更新

### api_client.py

```python
class QidianSaveClient:
    # ... 现有方法 ...

    def renew_api_key(self) -> dict:
        """重新生成 API Key"""
        return self._post("/api/auth/api-key/regenerate")

    def download_chapter(self, task_id: int, chapter_id: str, format: str = "text") -> requests.Response:
        """下载章节内容
        
        Args:
            format: "text" 或 "html"
        """
        resp = self.session.get(
            f"{self.base_url}/api/backup/{task_id}/chapters/{chapter_id}",
            params={"format": format},
            headers=self._headers(),
        )
        self._raise_on_error(resp)
        return resp

    # 删除 download_chapter_html() 方法
```

**变更要点**：
- 新增 `renew_api_key()` → `POST /api/auth/api-key/regenerate`
- `download_chapter()` 增加 `format` 参数，用 `?format=` 查询参数
- 删除 `download_chapter_html()`（不再需要）

### qidian_client.py

无改动。

## Step 3：CLI + 桌面端适配

### cli.py

新增子命令 `renew-api-key`：

```python
def cmd_renew_api_key(args):
    """重新生成 API Key"""
    client = _get_client(args)
    result = client.renew_api_key()
    api_key = result.get("api_key", "未知")
    click.echo(f"新的 API Key: {api_key}")
    click.echo("请更新你的 API Key 配置。")
```

注册命令：
```python
sub.add_parser("renew-api-key", help="重新生成 API Key")
```

修改 `cmd_backup()` 中调用 `download_chapter_html` 的地方，改为：
```python
resp = client.download_chapter(task_id, cid, format="html")
```

### backup_panel.py

`_download_all()` 中的 HTML 下载路径修改：
- `client.download_chapter_html(task_id, ch["chapterId"])` → `client.download_chapter(task_id, ch["chapterId"], format="html")`

### usage_panel.py

在用量信息下方增加「重新生成 API Key」按钮：

- 按钮样式：danger（红色）
- 点击行为：弹出 QMessageBox 确认对话框「确定要重新生成 API Key？旧的 Key 将立即失效」
- 确认后：调 `client.renew_api_key()`，在 info 标签显示新 Key
- 异常处理：网络错误时显示错误消息

## 不涉及

- Admin API 端点（`/api/admin/*`）
- 搜索/目录/书架（直调起点，不走服务端）
- ADB 工具
- 起点扫码登录

## 测试清单

- [ ] CLI: `python -m qidian_save renew-api-key` 正常返回新 Key
- [ ] CLI: `python -m qidian_save backup` 下载时 TXT / HTML 均正常
- [ ] 桌面端: 用量面板的「重新生成 API Key」按钮正常工作
- [ ] 桌面端: 备份面板下载功能正常
- [ ] 桌面端: 主题切换后按钮样式正确
- [ ] CLI: `python -m qidian_save --help` 显示新命令
