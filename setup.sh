#!/bin/bash
set -euo pipefail

# ============================================================
# 墨子 Harness · 环境锁定脚本
# 项目: zeroeye
# 生成: 2026-07-06
# ============================================================

echo "🔍 检查环境..."

# --- Python tooling for this bounty ---
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 未安装"
  exit 1
fi
echo "  ✅ Python: $(python3 --version)"

# --- Frontend dependencies for the lightweight build gate ---
if [ -f "frontend/package-lock.json" ]; then
  if ! command -v npm &>/dev/null; then
    echo "❌ npm 未安装，无法锁定 frontend 依赖"
    exit 1
  fi
  echo "📦 安装 frontend 依赖..."
  (cd frontend && npm ci)
else
  echo "  ⚠️ 未找到 frontend/package-lock.json，跳过 frontend 依赖安装"
fi

echo ""
echo "✅ 环境准备完成"
echo ""
echo "下一步:"
echo "  1. 确认 AGENTS.md 已配置"
echo "  2. git checkout -b feature/xxx 创建开发分支"
echo "  3. 开始写代码"
echo "  4. 跑 Harness: python3 -m py_compile tools/data_generator.py tools/test_data_generator.py && python3 -m unittest tools/test_data_generator.py && python3 -m py_compile tools/data_generator.py tools/test_data_generator.py && python3 build.py --module v2-market-stream"
echo "  5. 全绿后 git commit && git push origin feature/xxx"
