# AI Assistant Core Capabilities

This document defines the core architectural requirements for the AI Assistant product.

## 1. Architecture: CLI-First

All features MUST be accessible via CLI before being exposed through Web UI.

**CLI Structure:**
```
assistant/
├── cli/
│   ├── __main__.py      # python -m assistant.cli
│   ├── chat.py          # assistant chat "message"
│   ├── tools.py         # assistant tools list/call
│   ├── memory.py        # assistant memory search/clear
│   └── status.py        # assistant status
├── core/                # Core logic (HTTP-independent)
│   ├── chat_engine.py
│   ├── tool_executor.py
│   └── memory_store.py
└── server/              # HTTP layer (wraps core/)
```

**Benefits:**
- Claude Code can test any feature via CLI
- Scriptable and composable (Unix philosophy)
- Easier debugging than browser DevTools

## 2. Permission System

Configurable permission levels via environment variable: `ASSISTANT_PERMISSION_LEVEL`

| Level | Value | Access |
|-------|-------|--------|
| SANDBOX | 0 | Only `assistant/memory/` |
| LOCAL | 1 | Entire Genesis project |
| SYSTEM | 2 | Execute system commands (restricted) |
| FULL | 3 | Complete computer access (user's choice) |

**Implementation:**
```python
# assistant/core/permissions.py
import os
from enum import IntEnum

class PermissionLevel(IntEnum):
    SANDBOX = 0
    LOCAL = 1
    SYSTEM = 2
    FULL = 3

PERMISSION_LEVEL = PermissionLevel(
    int(os.getenv("ASSISTANT_PERMISSION_LEVEL", "1"))
)

def require_permission(level: PermissionLevel):
    """Decorator to enforce permission level"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            if PERMISSION_LEVEL < level:
                raise PermissionError(f"Requires {level.name} permission")
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

## 3. Process Lifecycle (Supervisor)

AI Assistant is managed by **Supervisor** for cross-platform compatibility.

**Why Supervisor (not launchd):**
- Works on macOS, Linux, and Windows (via WSL)
- Purpose-built for Python applications
- Better logging and control interface

**Supervisor Configuration:**
```ini
# assistant/service/supervisord.conf
[program:assistant]
command=python -m server.main
directory=%(ENV_GENESIS_DIR)s/assistant
environment=ASSISTANT_PERMISSION_LEVEL="1"
autorestart=true
startsecs=5
stopwaitsecs=10
stderr_logfile=%(ENV_HOME)s/Library/Logs/Genesis/assistant.err.log
stdout_logfile=%(ENV_HOME)s/Library/Logs/Genesis/assistant.out.log

[supervisorctl]
serverurl=unix:///tmp/supervisor.sock
```

**Graceful Restart Protocol:**
1. Claude Code updates assistant/ code
2. Claude Code runs: `supervisorctl restart assistant`
3. Supervisor sends SIGTERM to Assistant
4. Assistant saves state snapshot, exits cleanly
5. Supervisor starts new process
6. New process restores state snapshot

**State Snapshot:**
```python
# assistant/core/lifecycle.py
STATE_FILE = Path("assistant/memory/.state_snapshot.json")

def save_state():
    """Called before shutdown"""
    state = {
        "active_conversations": [...],
        "saved_at": datetime.now().isoformat()
    }
    STATE_FILE.write_text(json.dumps(state))

def restore_state():
    """Called on startup"""
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        STATE_FILE.unlink()
        return state
    return None
```

## 4. Health & Monitoring

**CLI:**
```bash
python -m assistant.cli health
# Output: {"status": "healthy", "uptime": 3600, "version": "0.1.0"}
```

**HTTP:**
```
GET /api/health
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "message_count": 42
}
```

## 5. Version Management

**Location:** `assistant/version.py`
```python
__version__ = "0.1.0"
```

**Git Tag Convention:**
- `assistant-v0.1.0` - AI Assistant releases
- `v1.0.0` - Major project milestones (includes Claude Code rules)

**Semantic Versioning:**
- MAJOR: Breaking changes to CLI/API
- MINOR: New features
- PATCH: Bug fixes

## 6. Logging

**Location:** `assistant/logs/`

**Files:**
- `assistant.log` - Main log (rotating, 10MB max, 5 backups)
- `error.log` - Errors only
- `access.log` - HTTP requests (optional)

**Format:**
```
2026-02-03 10:30:45 INFO [chat] User message received: "Hello"
2026-02-03 10:30:46 INFO [openai] API call: model=gpt-4o, tokens=150
2026-02-03 10:30:47 INFO [chat] Response sent: 120 chars
```

## 7. Claude Code Integration

Claude Code interacts with AI Assistant via:

1. **CLI commands** (primary method):
   ```bash
   python -m assistant.cli chat "Test message"
   python -m assistant.cli status
   python -m assistant.cli health
   ```

2. **Supervisor control**:
   ```bash
   supervisorctl restart assistant
   supervisorctl status assistant
   supervisorctl tail -f assistant
   ```

3. **Direct code modification** (then restart)

**Important:** AI Assistant does NOT display Claude Code development state. They are separate systems with separate concerns.
