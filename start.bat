@echo off
REM ============================================
REM qidian_save — 一键启动脚本 (Windows)
REM ============================================

REM 强制使用 UTF-8 编码
chcp 65001 >nul

cd /d "%~dp0client"

echo 正在安装/更新依赖...
pip install -e . -q

echo.
echo 启动 qidian_save...
python -m qidian_save desktop

pause
