#!/bin/bash
# Hook: SessionEnd (8)
# Purpose: Commit changes to git, push to remote, then trigger next iteration

# Auto-detect GENESIS_DIR from script location (hooks/ -> parent)
GENESIS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOOP_FLAG_FILE="$GENESIS_DIR/hooks/loop_claude_code.txt"
RUNLOG_DIR="$GENESIS_DIR/claude_iteration/runlog"

# Get recent runlog filenames (up to 3)
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

# Git commit and push changes
git_sync() {
    cd "$GENESIS_DIR" || return 1

    # Check if there are any changes to commit
    if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
        echo "📝 No changes to commit"
        return 0
    fi

    # Get the latest runlog for commit message
    LATEST_RUNLOG=$(ls -1 "$RUNLOG_DIR"/*.md 2>/dev/null | sort -r | head -1 | xargs basename 2>/dev/null)
    COMMIT_MSG="Auto-commit: ${LATEST_RUNLOG:-$(date '+%Y-%m-%d %H:%M')}"

    # Stage all changes
    git add -A

    # Commit
    echo "📦 Committing changes: $COMMIT_MSG"
    git commit -m "$COMMIT_MSG" --no-verify 2>/dev/null

    # Push to remote
    echo "🚀 Pushing to remote..."
    if git push 2>/dev/null; then
        echo "✅ Changes pushed to remote"
    else
        echo "⚠️  Push failed (will retry next iteration)"
    fi
}

# Always try to sync git changes
git_sync

# Check loop_claude_code.txt file
if [ ! -f "$LOOP_FLAG_FILE" ]; then
    echo "⏹️  Auto-loop disabled: $LOOP_FLAG_FILE not found"
    exit 0
fi

LOOP_VALUE=$(cat "$LOOP_FLAG_FILE" 2>/dev/null | tr -d '[:space:]')

if [ "$LOOP_VALUE" != "true" ]; then
    echo "⏹️  Auto-loop disabled: loop_claude_code.txt is '$LOOP_VALUE' (not 'true')"
    exit 0
fi

# Get recent runlog list
RECENT_RUNLOGS=$(get_recent_runlogs)

# Start next iteration in new Terminal window after 3 seconds
echo "🔄 Auto-loop enabled. Starting next iteration in 3 seconds..."
echo "   Recent runlogs: $RECENT_RUNLOGS"

(sleep 3 && osascript -e "
    tell application \"Terminal\"
        activate
        do script \"cd '$GENESIS_DIR' && claude --dangerously-skip-permissions 'Execute one iteration per the contract in CLAUDE.md. Check GitHub Issues first, then claude_iteration/state.md for next step. Recent runlogs: $RECENT_RUNLOGS (read more logs as needed)'\"
    end tell
") &
disown

exit 0
