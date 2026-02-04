#!/bin/bash
# 启动自动循环
# 每次迭代完成后，Stop hook 会在新 Terminal 窗口中启动下一轮

GENESIS_DIR="/Volumes/Storage/Server/Startup/Genesis"
LOOP_FLAG_FILE="$GENESIS_DIR/hooks/loop_claude_code.txt"
RUNLOG_DIR="$GENESIS_DIR/claude_iteration/runlog"

# 获取最近的 runlog 文件名（最多 3 个）
get_recent_runlogs() {
    if [ -d "$RUNLOG_DIR" ]; then
        local files=$(ls -1 "$RUNLOG_DIR"/*.md 2>/dev/null | sort -r | head -3 | xargs -I {} basename {} 2>/dev/null)
        if [ -n "$files" ]; then
            echo "$files" | paste -sd ',' - | sed 's/,/, /g'
        else
            echo "(no runlogs yet)"
        fi
    else
        echo "(runlog dir not found)"
    fi
}

# 设置循环标志为 true
echo "true" > "$LOOP_FLAG_FILE"

# 获取最近的 runlog 列表
RECENT_RUNLOGS=$(get_recent_runlogs)

echo "================================================"
echo "自动循环已启用"
echo "每次迭代完成后会自动在新 Terminal 窗口中启动下一轮"
echo "停止循环: ./stop-loop.sh"
echo "Recent runlogs: $RECENT_RUNLOGS"
echo "================================================"
echo ""

# 启动第一轮
cd "$GENESIS_DIR"
claude --dangerously-skip-permissions "Execute one iteration per the contract in CLAUDE.md. Check GitHub Issues first, then claude_iteration/state.md for next step. Recent runlogs: $RECENT_RUNLOGS"
