#!/bin/bash
# Stop the Genesis Multi-Agent Loop

# Auto-detect GENESIS_DIR from script location
GENESIS_DIR="$(cd "$(dirname "$0")" && pwd)"
LOOP_FLAG_FILE="$GENESIS_DIR/hooks/loop_multi_agent.txt"

echo "Stopping multi-agent loop..."
echo "false" > "$LOOP_FLAG_FILE"
echo "Loop flag set to 'false'. The loop will stop after the current iteration completes."
echo ""
echo "To force stop immediately, find and kill the process:"
echo "  ps aux | grep start-multi-agent-loop"
echo "  kill <PID>"
