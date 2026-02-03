#!/bin/bash
# Hook: PostToolUse (2)
# Purpose: Log all tool usage for auditability

LOGDIR="/Users/zelin/Startups/Genesis/claude_iteration/runlog"
LOGFILE="$LOGDIR/tool-usage-$(date +%Y-%m-%d).log"

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"' 2>/dev/null || echo "unknown")
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

echo "[$TIMESTAMP] $TOOL_NAME" >> "$LOGFILE"
exit 0
