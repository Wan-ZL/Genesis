#!/bin/bash
# Hook: SessionStart (6)
# Purpose: Initialize session, create daily log file

# Auto-detect GENESIS_DIR from script location (hooks/ -> parent)
GENESIS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOGDIR="$GENESIS_DIR/claude_iteration/runlog"
TODAY=$(date +%Y-%m-%d)
SESSION_LOG="$LOGDIR/session-$TODAY.log"

echo "=== Session started at $(date +"%Y-%m-%d %H:%M:%S") ===" >> "$SESSION_LOG"
exit 0
