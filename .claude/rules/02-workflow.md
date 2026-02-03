# Workflow Rules (Iteration-first)

## Single-iteration rule
Each run must produce one incremental improvement and then exit.
Do not start multi-day refactors unless it is explicitly scoped and tracked as milestones.

## Issue-driven development
- If GitHub Issues exist: treat them as source of truth.
- Every issue should have acceptance criteria.
- If acceptance criteria is missing, propose a minimal version in the issue comment (do not ask the user in chat).
- **When all acceptance criteria are met, close the issue with `gh issue close <number> -c "Completed: <summary>"`.**

## Testing rules
- Add tests for deterministic logic.
- Add evals for subjective / LLM behavior.
- Prefer automated checks on every iteration.

## Logging rules
- Every run writes `claude_iteration/runlog/...`.
- Every run updates `claude_iteration/state.md`.
- If blocked, write a concrete unblock plan.

## PR etiquette
- Small PRs, clear titles.
- Include "How to test" in PR description.
