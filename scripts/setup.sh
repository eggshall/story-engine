#!/usr/bin/env bash
# 故事引擎 — 开发环境初始化脚本
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== 故事引擎 — 环境初始化 ==="
echo ""

# 1. 创建虚拟环境
if [ ! -d .venv ]; then
    echo "[1/4] 创建虚拟环境..."
    python3 -m venv .venv
else
    echo "[1/4] 虚拟环境已存在，跳过"
fi

# 2. 激活并安装依赖
echo "[2/4] 安装项目依赖..."
source .venv/bin/activate
pip install --quiet -e ".[dev]" 2>/dev/null || pip install --quiet -e .
echo "  完成"

# 3. 创建示例数据
echo "[3/4] 创建示例数据..."
story character example 2>/dev/null || true
story lore example 2>/dev/null || true
echo "  完成"

# 4. 验证
echo "[4/4] 验证安装..."
story info
echo ""
echo "=== 初始化完成 ==="
echo "运行 source .venv/bin/activate 激活环境"
echo "运行 story --help 查看可用命令"
