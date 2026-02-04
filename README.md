# Genesis

An experiment in building an AI that builds itself.

## What is this?

Genesis is a self-evolving AI assistant where **Claude Code (an AI) is the primary developer**. The human provides direction via GitHub Issues; the AI reads them, writes code, runs tests, logs progress, and repeats—building an always-on assistant one iteration at a time.

```
┌─────────────────────────────────────────────────────────┐
│                   The Loop                              │
│                                                         │
│   Human creates Issue → Claude Code reads Issue         │
│         ↑                      ↓                        │
│   Human reviews PR    ←  Claude Code implements         │
│                              ↓                          │
│                      Claude Code tests                  │
│                              ↓                          │
│                      Claude Code commits                │
│                              ↓                          │
│                      State persisted → Next iteration   │
└─────────────────────────────────────────────────────────┘
```

## Two Systems

| | Claude Code (Builder) | AI Assistant (Product) |
|---|---|---|
| Role | Developer / Builder | User-facing product |
| Memory | `.claude/` + `claude_iteration/` | `assistant/memory/` |
| Runs | Iteratively (one task, then exit) | 24/7 always-on |
| Code | Reads & writes `assistant/` | Lives in `assistant/` |

The builder improves the product. They are separate systems with separate concerns.

## Features Built So Far

- **Web UI**: Chat interface with conversation history, file upload, metrics dashboard
- **Multimodal**: Image and PDF upload with vision model support
- **Dual LLM**: Claude API + OpenAI fallback
- **Tool System**: Extensible tool registry (datetime, calculator, web fetch)
- **Eval Framework**: Automated testing for LLM behavior
- **24/7 Service**: Supervisor-managed process with auto-restart
- **CI/CD**: GitHub Actions for automated testing (Python 3.9-3.11)
- **Mobile-friendly**: Responsive UI with touch support

## Project Structure

```
Genesis/
├── .claude/              # Claude Code's "constitution" and rules
│   ├── CLAUDE.md         # Core instructions for Claude Code
│   └── rules/            # Modular rules (workflow, safety, etc.)
├── claude_iteration/     # Claude Code's working memory
│   ├── state.md          # Current focus and next step
│   ├── roadmap.md        # High-level goals
│   ├── backlog.md        # Task queue
│   └── runlog/           # Log of every iteration
├── assistant/            # The AI Assistant product
│   ├── server/           # FastAPI backend
│   ├── ui/               # Web frontend
│   ├── memory/           # SQLite + uploaded files
│   ├── evals/            # Eval framework
│   └── service/          # Supervisor config
├── hooks/                # Claude Code automation hooks
└── start-loop.sh         # Trigger continuous iteration
```

## Quick Start

```bash
# Run the AI Assistant
cd assistant
pip install -r requirements.txt
python -m server.main
# Visit http://127.0.0.1:8080

# Or install as 24/7 service (macOS)
./service/assistant-service.sh install
./service/assistant-service.sh start

# Run tests
python -m pytest tests/ -v
```

## How Claude Code Works

1. **Reads context**: `.claude/CLAUDE.md`, rules, `state.md`, recent runlogs
2. **Picks work**: GitHub Issues (priority) or backlog items
3. **Does ONE increment**: Implement, test, document
4. **Persists memory**: Writes runlog, updates `state.md`
5. **Exits cleanly**: Ready for next iteration

All progress lives in the repo—Claude Code has no memory between runs except what's written to files.

## Contributing

Open a GitHub Issue with clear acceptance criteria. Claude Code will pick it up and implement it. You review the PR.