#!/bin/bash
# 停止自动循环

GENESIS_DIR="/Volumes/Storage/Server/Startup/Genesis"
LOOP_FLAG_FILE="$GENESIS_DIR/hooks/loop_claude_code.txt"

# 设置循环标志为 false
echo "false" > "$LOOP_FLAG_FILE"
echo "自动循环已停止（当前迭代会完成，之后不再启动新迭代）"
