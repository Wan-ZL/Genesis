# Safety Rules (Minimum Baseline)

## Secrets
- Never print, commit, or upload secrets.
- Never copy `.env`, tokens, cookies, ssh keys into logs or code.

## Dangerous operations
- No privilege escalation.
- No destructive filesystem operations.
- If a risky action seems required, write a proposal in agent/runlog and choose a safer alternative.

## Auditability
- Prefer changes that are reviewable and testable.
- Log external calls and major actions.
