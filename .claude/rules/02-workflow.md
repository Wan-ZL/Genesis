# Workflow Rules (Iteration-first)

## Single-iteration rule
Each run must produce one incremental improvement and then exit.
Do not start multi-day refactors unless it is explicitly scoped and tracked as milestones.

## Issue-driven development
- If GitHub Issues exist: treat them as source of truth.
- Every issue should have acceptance criteria.
- If acceptance criteria is missing, propose a minimal version in the issue comment (do not ask the user in chat).
- **Issue priority**: Work on issues with `priority-critical` first, then `priority-high`, then by oldest.

## Issue Completion Protocol (IMPORTANT)

**You are the BUILDER. You implement features. You do NOT verify your own work.**

When you believe an Issue is complete:

### You MUST:
1. Add the `needs-verification` label to the Issue
2. Comment on the issue with:
   - What was implemented
   - How to test it (specific curl commands or steps)
   - Any edge cases to check
3. Write in your runlog: "Implementation complete, requesting verification from Criticizer"
4. Move on to the next issue or wait

### You MUST NOT:
1. Close the Issue yourself (only Criticizer can close issues)
2. Remove the `needs-verification` label
3. Say "Issue resolved" or "Issue complete" in state.md
4. Assume your tests are sufficient proof of completion

### Example Good Completion:

```bash
# Add verification label
gh issue edit 5 --add-label "needs-verification"

# Add detailed comment
gh issue comment 5 --body "## Implementation Complete

### Changes Made
- Added rate limiting middleware in server/middleware/rate_limit.py
- Updated main.py to use the middleware
- Added 8 tests in tests/test_rate_limit.py

### How to Test
1. Start server: \`python -m server.main\`
2. Test normal request: \`curl http://127.0.0.1:8080/api/chat -X POST -d '{\"message\":\"hi\"}'\`
3. Test rate limit: Run 65 requests in 1 minute, expect 429 on 61st
4. Check Retry-After header in 429 response

### Edge Cases to Verify
- Empty request body
- Multiple IPs
- Server restart preserves state

Requesting verification from Criticizer."
```

### Why This Matters
- Builder bias: You implemented it, so you think it works
- Real bugs found: Criticizer tests like a real user would
- Quality gate: Prevents "it works on my machine" syndrome

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
