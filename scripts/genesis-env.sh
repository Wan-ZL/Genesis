#!/bin/bash
# Genesis Environment Configuration
# Source this file in shell scripts to get GENESIS_DIR and common settings
#
# Usage in other scripts:
#   SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
#   source "$SCRIPT_DIR/../scripts/genesis-env.sh" 2>/dev/null || source "$(dirname "$SCRIPT_DIR")/scripts/genesis-env.sh"
#
# Or if you know the exact location:
#   source /path/to/Genesis/scripts/genesis-env.sh

# Auto-detect GENESIS_DIR if not already set
if [ -z "$GENESIS_DIR" ]; then
    # Try to detect based on this script's location
    if [ -n "${BASH_SOURCE[0]}" ]; then
        _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        GENESIS_DIR="$(dirname "$_SCRIPT_DIR")"
        unset _SCRIPT_DIR
    fi
fi

# Validate GENESIS_DIR exists and has expected structure
validate_genesis_dir() {
    if [ -z "$GENESIS_DIR" ]; then
        echo "ERROR: GENESIS_DIR not set and could not be auto-detected" >&2
        echo "Set it manually: export GENESIS_DIR=/path/to/Genesis" >&2
        return 1
    fi

    if [ ! -d "$GENESIS_DIR" ]; then
        echo "ERROR: GENESIS_DIR does not exist: $GENESIS_DIR" >&2
        return 1
    fi

    # Check for key files/dirs that indicate this is the Genesis project
    if [ ! -f "$GENESIS_DIR/.claude/CLAUDE.md" ]; then
        echo "ERROR: $GENESIS_DIR does not appear to be a Genesis project (missing .claude/CLAUDE.md)" >&2
        return 1
    fi

    return 0
}

# Export commonly used paths
export GENESIS_DIR
export ASSISTANT_DIR="${GENESIS_DIR}/assistant"
export CLAUDE_ITERATION_DIR="${GENESIS_DIR}/claude_iteration"
export HOOKS_DIR="${GENESIS_DIR}/hooks"

# Validate on source (optional - uncomment if you want strict validation)
# validate_genesis_dir || return 1
