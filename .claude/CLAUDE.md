# Project Memory: Always-on Multimodal AI Assistant (Mac mini)

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

You are the BUILDER in a 3-agent system:
- **You (Builder)**: Implement features, write tests, commit code
- **Criticizer**: Verifies your work by running actual API tests
- **Planner**: Sets priorities, maintains roadmap, creates strategic issues

**Critical Rule**: You CANNOT close issues. Only the Criticizer can close issues after verification.

When you complete an issue:
1. Add `needs-verification` label: `gh issue edit <n> --add-label "needs-verification"`
2. Comment with test instructions
3. Move on to the next issue

See `.claude/rules/02-workflow.md` for the complete Issue Completion Protocol.

## 3) Execution contract (EVERY run)
Follow these steps in order:
A) Read:
   - `.claude/CLAUDE.md`
   - `.claude/rules/*`
   - `claude_iteration/state.md`
   - Latest 3 runlogs from `claude_iteration/runlog/` (for continuity with previous sessions)
B) Discover work:
   - If any GitHub Issues are open, pick the highest-priority one.
   - Otherwise, pick the best item from `claude_iteration/backlog.md`.
   - If no GitHub Issues AND backlog is empty/all-done, run `./stop-loop.sh` and exit.
C) Do ONE smallest meaningful increment only:
   - Implement or refactor.
   - Add/extend tests and/or evals.
   - Update docs.
D) Validate:
   - Run the project's tests (or write clearly why tests cannot run).
E) Persist memory (Claude Code must do this, not hooks):
   - Write a run log to `claude_iteration/runlog/YYYY-MM-DD_HHMM.md` with:
     ```
     # Run Log: YYYY-MM-DD HH:MM
     ## Focus
     [What issue/task was worked on]
     ## Changes
     - [File changed]: [what changed]
     ## Result
     [SUCCESS/PARTIAL/BLOCKED]
     ## Next
     [Single next step]
     ```
   - Update `claude_iteration/state.md` with (1) what changed (2) what to do next
   - Update `claude_iteration/roadmap.md` if milestone or priority changed
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
