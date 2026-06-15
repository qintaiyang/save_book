@echo off
REM ============================================
REM qidian_save — 一键启动脚本 (Windows)
REM ============================================

cd /d "%~dp0"

echo 正在安装/更新依赖...
pip install -e client -q

echo.
echo 启动 qidian_save...
python run_desktop.py

pause
