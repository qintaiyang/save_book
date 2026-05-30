#!/bin/bash
# ============================================
# qidian_save — 一键启动脚本 (Linux/macOS)
# ============================================

cd "$(dirname "$0")/client"

echo "正在安装/更新依赖..."
pip install -e . -q

echo ""
echo "启动 qidian_save..."
python -m qidian_save desktop
