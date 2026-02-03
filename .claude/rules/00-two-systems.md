# Two Systems - Important Distinction

This project has two completely different systems. Do not confuse them:

## 1. Claude Code (Builder)
- **Role**: Development tool used to build the AI Assistant product
- **Execution**: Iterative - executes one step then exits
- **Memory location**: `.claude/CLAUDE.md` + `.claude/rules/*.md` (auto-loaded)
- **State/Plan location**: `agent/state.md`, `agent/roadmap.md`, `agent/backlog.md`
- **Log location**: `agent/runlog/`
- **Purpose**: Remember "how to develop, progress so far, what to do next"

## 2. AI Assistant (Product)
- **Role**: The product being built, user-facing
- **Execution**: 24/7 always-on service
- **Code location**: `assistant/`
- **Memory location**: Subdirectory under `assistant/` (to be designed and implemented)
- **Purpose**: Remember "what user said, user preferences, conversation history"

## Key Differences

| | Claude Code | AI Assistant |
|---|---|---|
| Identity | Developer/Builder | Product |
| Memory | `.claude/` + `agent/` | `assistant/memory/` (to be implemented) |
| Serves | Project development workflow | End users |

## Rules
- Modifying `.claude/` or `agent/` = Changing how Claude Code works
- Modifying `assistant/` = Building product features
- Do not confuse the two
