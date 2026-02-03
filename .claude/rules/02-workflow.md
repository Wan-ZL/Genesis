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
- **Before closing any issue**: Must perform end-to-end verification:
  1. Run all unit tests (`pytest tests/`)
  2. Start the actual service and manually verify the fix works
  3. Test edge cases (error states, empty data, boundary conditions)
  4. Document test steps and results in the runlog
- If E2E testing is not possible (e.g., requires user interaction), explicitly note this in the issue close comment.
- **Use terminal for manual testing**: You have access to `curl`, `python3`, and other CLI tools. Use them to:
  - Test API endpoints directly (`curl http://127.0.0.1:8080/api/...`)
  - Verify response structure matches frontend expectations
  - Test both success and error scenarios
  - Never assume code works just because unit tests pass

## Logging rules
- Every run writes `claude_iteration/runlog/...`.
- Every run updates `claude_iteration/state.md`.
- If blocked, write a concrete unblock plan.

## PR etiquette
- Small PRs, clear titles.
- Include "How to test" in PR description.
