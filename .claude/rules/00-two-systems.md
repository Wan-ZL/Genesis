# Two Systems - Important Distinction

This project has two completely different systems. Do not confuse them:

## 1. Claude Code (Builder)
- **Role**: Development tool used to build the AI Assistant product
- **Execution**: Iterative - executes one step then exits
- **Memory location**: `.claude/CLAUDE.md` + `.claude/rules/*.md` (auto-loaded)
- **State/Plan location**: `claude_iteration/state.md`, `claude_iteration/roadmap.md`, `claude_iteration/backlog.md`
- **Log location**: `claude_iteration/runlog/`
- **Purpose**: Remember "how to develop, progress so far, what to do next"

## 2. AI Assistant (Product)
- **Role**: The product being built, user-facing
- **Execution**: 24/7 always-on service (managed by Supervisor)
- **Code location**: `assistant/`
- **Memory location**: `assistant/memory/` (SQLite + files)
- **Purpose**: Remember "what user said, user preferences, conversation history"

## Key Differences

| | Claude Code | AI Assistant |
|---|---|---|
| Identity | Developer/Builder | Product |
| Memory | `.claude/` + `claude_iteration/` | `assistant/memory/` |
| Serves | Project development workflow | End users |
| Version | Git tags (project-level) | `assistant/version.py` |

## Rules
- Modifying `.claude/` or `claude_iteration/` = Changing how Claude Code works
- Modifying `assistant/` = Building product features
- AI Assistant does NOT display Claude Code state (they are separate systems)
- Do not confuse the two
