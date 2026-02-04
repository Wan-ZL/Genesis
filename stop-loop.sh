#!/bin/bash
# 停止自动循环

# Auto-detect GENESIS_DIR from script location
GENESIS_DIR="$(cd "$(dirname "$0")" && pwd)"
LOOP_FLAG_FILE="$GENESIS_DIR/hooks/loop_claude_code.txt"

# 设置循环标志为 false
echo "false" > "$LOOP_FLAG_FILE"
echo "自动循环已停止（当前迭代会完成，之后不再启动新迭代）"
