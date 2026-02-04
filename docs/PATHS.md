# Genesis Path Configuration

## Canonical Project Location

Genesis can run from any directory. The project uses **auto-detection** and **environment variables** to determine paths, rather than hardcoded absolute paths.

## GENESIS_DIR Environment Variable

`GENESIS_DIR` is the root directory of the Genesis project. All scripts and services should use this variable (or auto-detect it) rather than hardcoding paths.

### For Shell Scripts

Scripts in the project root auto-detect GENESIS_DIR:

```bash
# Auto-detect from script location
GENESIS_DIR="$(cd "$(dirname "$0")" && pwd)"
```

Scripts in subdirectories (like `hooks/`) navigate up:

```bash
# Auto-detect from hooks/ -> project root
GENESIS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
```

### For Services

The Supervisor service uses the `GENESIS_DIR` environment variable:

```ini
# In supervisord.conf
directory=%(ENV_GENESIS_DIR)s/assistant
environment=PYTHONPATH="%(ENV_GENESIS_DIR)s/assistant"
```

The `assistant-service.sh` script exports `GENESIS_DIR` before starting Supervisor.

### For Python Code

Python code uses relative paths from `__file__`:

```python
# In config.py
BASE_DIR = Path(__file__).parent
DATABASE_PATH = BASE_DIR / "memory" / "conversations.db"
```

### For Documentation

Use `$GENESIS_DIR` placeholder in documentation examples:

```bash
cd $GENESIS_DIR/assistant
python -m server.main
```

## Common Paths

| Path | Description |
|------|-------------|
| `$GENESIS_DIR` | Project root |
| `$GENESIS_DIR/assistant` | AI Assistant application |
| `$GENESIS_DIR/claude_iteration` | Claude Code (Builder) state |
| `$GENESIS_DIR/criticizer_iteration` | Criticizer agent state |
| `$GENESIS_DIR/planner_iteration` | Planner agent state |
| `$GENESIS_DIR/hooks` | Claude Code hooks |
| `$GENESIS_DIR/scripts` | Utility scripts |

## Known Exceptions

### Claude Code Hooks (`.claude/settings.json`)

The Claude Code hook configuration requires an absolute path because hooks are executed from a global context (not the project directory). This is the one place where an absolute path is necessary:

```json
{
  "hooks": {
    "Stop": [{
      "command": "bash /path/to/Genesis/hooks/8-SessionEnd-trigger-next.sh"
    }]
  }
}
```

If you move the Genesis project, you must update `.claude/settings.json` manually.

## History

Previously, the codebase had inconsistent hardcoded paths:
- `/Users/zelin/Startups/Genesis` (old location)
- `/Volumes/Storage/Server/Startup/Genesis` (migrated location)

These have been replaced with auto-detection. See Issue #9 for details.

## Validation

If you need to validate GENESIS_DIR, use the utility script:

```bash
source scripts/genesis-env.sh
validate_genesis_dir || echo "Invalid GENESIS_DIR"
```

This checks that:
1. GENESIS_DIR is set
2. The directory exists
3. It contains expected Genesis project files (`.claude/CLAUDE.md`)
