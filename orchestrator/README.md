# Genesis Orchestrator - Self-Healing Mechanism

This directory contains state files for the Genesis autonomous loop self-healing mechanisms.

## Overview

The Genesis multi-agent loop (`start-multi-agent-loop.sh`) includes several self-healing mechanisms to detect and recover from stuck states:

1. **Heartbeat Detection** - Detects when Claude Code is stuck waiting for subprocess output
2. **Circuit Breaker** - Stops the loop after consecutive iterations with no progress
3. **Zombie Cleanup** - Cleans up orphaned processes after each agent run

## How It Works

### Heartbeat System

```
Claude Code tool call → PostToolUse Hook → genesis-heartbeat.sh → /tmp/genesis_heartbeat.json
                                                                         ↓
                         start-multi-agent-loop.sh checks every 60s
                                                                         ↓
                         If heartbeat > 15 min old → Agent is STUCK → Kill & continue
```

**Key insight**: When Claude is waiting for a subprocess (e.g., pytest hanging), it makes no tool calls, so the heartbeat stops updating.

### Circuit Breaker

Based on the [Ralph](https://github.com/frankbria/ralph-claude-code) project's pattern:

| State | Condition | Action |
|-------|-----------|--------|
| CLOSED | Progress detected (git changes) | Continue normally |
| HALF_OPEN | 3+ iterations without progress | Warn but continue |
| OPEN | 5+ iterations without progress | Stop the loop |

"Progress" is defined as:
- Uncommitted changes in working tree
- Staged changes in index
- New untracked files

### Zombie Cleanup

After each agent run, the system cleans up:
- Stuck `python -m server.main` processes
- Hung `pytest` processes
- Processes occupying port 8080

## Files

| File | Purpose |
|------|---------|
| `.circuit_breaker.json` | Circuit breaker state (auto-created) |
| `README.md` | This documentation |

## Configuration

In `start-multi-agent-loop.sh`:

```bash
HEARTBEAT_STALE_MINUTES=15      # Minutes before considering agent stuck
HEARTBEAT_CHECK_INTERVAL=60     # Seconds between heartbeat checks
CB_WARNING_THRESHOLD=3          # Iterations without progress before warning
CB_STOP_THRESHOLD=5             # Iterations without progress before stopping
```

## External Dependencies

### Heartbeat Hook

File: `~/.local/bin/genesis-heartbeat.sh`
Trigger: PostToolUse hook in `~/.claude/settings.json`

### Claude Settings

File: `~/.claude/settings.json`

Required configuration:
```json
{
  "env": {
    "BASH_DEFAULT_TIMEOUT_MS": "1800000",
    "BASH_MAX_TIMEOUT_MS": "7200000"
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/Users/zelin/.local/bin/genesis-heartbeat.sh"
          }
        ]
      }
    ]
  }
}
```

## Testing

```bash
# 1. Test heartbeat script
~/.local/bin/genesis-heartbeat.sh test_tool
cat /tmp/genesis_heartbeat.json
# Should see: {"agent": "...", "timestamp": "...", "tool": "test_tool", "pid": ...}

# 2. Test PostToolUse hook (run any Claude Code command)
# Then check: cat /tmp/genesis_heartbeat.json

# 3. Test stale heartbeat detection
echo '{"timestamp": "'$(date -v-20M -Iseconds)'"}' > /tmp/genesis_heartbeat.json
# The next heartbeat check should detect staleness

# 4. Test circuit breaker
# Run 5 iterations that make no changes
# Loop should automatically stop
```

## Troubleshooting

### Loop stops unexpectedly

Check circuit breaker state:
```bash
cat orchestrator/.circuit_breaker.json
```

If `state: "OPEN"`, the loop stopped due to no progress. Options:
1. Make a change and restart
2. Delete the file to reset: `rm orchestrator/.circuit_breaker.json`

### Agent marked as stuck but was working

Increase `HEARTBEAT_STALE_MINUTES` if your tasks legitimately take longer than 15 minutes without tool calls.

### Zombie processes still running

The cleanup function handles common patterns. Add more patterns to `cleanup_zombie_processes()` if needed.

## References

- [parallel-cc](https://github.com/frankbria/parallel-cc) - PostToolUse heartbeat pattern
- [Ralph](https://github.com/frankbria/ralph-claude-code) - Circuit breaker pattern
- [Claude Code Timeout Configuration](https://github.com/anthropics/claude-code/issues/5615)
