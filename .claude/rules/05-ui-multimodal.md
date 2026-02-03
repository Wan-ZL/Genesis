# UI + Multimodal Rules

## UI v1
- Implement a minimal web UI:
  - input box for user messages
  - message history
  - status panel showing:
    - current focus (from agent/state.md)
    - last run status (from latest runlog)
- Keep it simple, no auth in v1 (local-only).

## Multimodal v1
- Support image and PDF upload to a local artifacts folder.
- Store metadata + summary so future runs can reference it without re-reading everything.
