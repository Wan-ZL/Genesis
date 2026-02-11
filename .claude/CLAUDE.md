# Project Memory: Always-on Multimodal AI Assistant (Mac mini)

## Quick Commands
```bash
# Tests (from project root)
cd assistant && python3 -m pytest tests/ -q        # Full suite (~970 tests, ~35s)
cd assistant && python3 -m pytest tests/ -x -q     # Stop on first failure
cd assistant && python3 -m pytest tests/test_chat_api.py -v  # Single file

# Run server
cd assistant && python3 -m server.main              # http://127.0.0.1:8080

# Orchestration loop
./start-multi-agent-loop.sh                         # Builder → Criticizer → Planner
./stop-multi-agent-loop.sh                          # Graceful stop
```

## 0) Background, why this repo exists
This repo is an experiment to build a self-evolving AI assistant.
Claude Code is the primary builder and tester.
The user triggers a hook after each completed task and re-runs the SAME prompt, so progress must persist in-repo and never rely on chat memory.

Key loop:
- User provides a stable English prompt.
- Claude Code executes ONE iteration, updates state, logs work, and exits cleanly.
- User triggers the next iteration by running the same prompt again.
- When user has new needs, they create a GitHub Issue, which becomes the new top priority.

## 1) Non-negotiable objectives
1. Long-term memory: all important context and plans must live in this repo.
2. Long-term planning + short-term execution: always maintain a roadmap and a next-step state.
3. Tool creation + tool use: create tools when needed, register them, test them, document them.
4. Multimodal: support images + PDFs (and later audio if needed), especially for UI work.
5. 24/7: the assistant system runs continuously on the user's Mac mini.

## 2) Definitions
- "Assistant Runtime": the always-on service the user interacts with (web UI initially).
- "Builder": Claude Code (YOU), running in iterations to implement features and fix bugs.
- "Criticizer": Subagent that verifies your work by actually running the product.
- "Planner": Subagent that maintains roadmap and sets priorities.
- "Persistent memory": `.claude/` + `claude_iteration/` documents that are loaded every run.

## 2.5) Multi-Agent System (IMPORTANT)

You are the BUILDER. You CANNOT close issues — only Criticizer can.
When done: `gh issue edit <N> --add-label "needs-verification"` + comment with test steps.
Full protocol: `.claude/rules/02-workflow.md` and `.claude/rules/08-multi-agent-system.md`

## 3) Execution contract (EVERY run)
Follow these steps in order:
A) Read: `claude_iteration/state.md` + latest 3 runlogs from `claude_iteration/runlog/`
B) Discover work:
   - If any GitHub Issues are open, pick the highest-priority one.
   - Otherwise, pick the best item from `claude_iteration/backlog.md`.
   - If no GitHub Issues AND backlog is empty/all-done, run `./stop-loop.sh` and exit.
C) Do ONE smallest meaningful increment only.
D) Validate: `cd assistant && python3 -m pytest tests/ -q`
E) Persist memory (Claude Code must do this, not hooks):
   - Write runlog to `claude_iteration/runlog/YYYY-MM-DD_HHMM.md` (follow format of existing logs)
   - Update `claude_iteration/state.md` (what changed + single next step)
F) Exit cleanly.

## 4) Output format at end of every run
Print:
- Summary (what changed)
- How to test locally
- Files touched
- Next step (from claude_iteration/state.md)

And end with:

[RUN_STATUS]
result = SUCCESS | NEEDS_INPUT | BLOCKED
next = CONTINUE | WAIT_FOR_USER | WAIT_FOR_REVIEW
state_file = claude_iteration/state.md
runlog_file = claude_iteration/runlog/<latest>.md

## 5) Current user preferences
- Deployment: always-on on Mac mini.
- UI: simplest web page is fine now, can evolve later.
- Network: no domain restrictions (but must log external calls and never leak secrets).

## 6) Git workflow
- Prefer feature branches and PRs for reviewable evolution.
- If working alone and speed is needed, use direct commits only for tiny changes.
- Never commit secrets.

## 7) Roadmap pointer
- High-level goals: `planner_iteration/roadmap.md` (owned by Planner)
- Builder state + working context: `claude_iteration/state.md`
- Self-improvement tasks: `claude_iteration/backlog.md`
- Criticizer state: `criticizer_iteration/state.md`
- Planner state: `planner_iteration/state.md`
- Architectural decisions: `planner_iteration/decisions/`

## 8) Key files
- `assistant/server/main.py` — FastAPI server entry point (port 8080)
- `assistant/config.py` — All settings, model list, API keys
- `assistant/server/routes/chat.py` — Chat + streaming endpoints
- `assistant/server/services/memory.py` — SQLite conversation storage
- `assistant/tests/` — 970+ tests
- `start-multi-agent-loop.sh` — Orchestration loop (timeouts: Bash=10min, heartbeat=15min, max=45min)
- `orchestrator/.circuit_breaker.json` — Loop health state (auto-resets on start)
