"""启动入口 — 支持桌面模式（无参数）和 CLI 模式（有参数）"""
import sys, os

# 确保包在搜索路径中，使相对导入正常工作
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

desktop_flags = {"--debug", "-debug"}
if len(sys.argv) > 1 and not set(sys.argv[1:]).issubset(desktop_flags):
    # 有命令行参数 → CLI 模式
    from qidian_save.cli import main as cli_main
    cli_main()
else:
    # 无参数 → 启动桌面端
    from qidian_save.desktop.app import main as desktop_main
    desktop_main()
