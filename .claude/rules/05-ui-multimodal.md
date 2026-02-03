# UI + Multimodal Rules

## UI Architecture
- **CLI-first**: All features must have CLI interface before Web UI
- Web UI is a wrapper around CLI commands
- Claude Code tests and interacts with Assistant via CLI

## UI v1
- Implement a minimal web UI:
  - input box for user messages
  - message history
  - status panel showing AI Assistant's own status:
    - version number
    - uptime
    - health status
    - message count
- Keep it simple, no auth in v1 (local-only)
- **Note**: AI Assistant does NOT display Claude Code development state (they are separate systems)

## Multimodal v1
- Support image and PDF upload to `assistant/memory/files/`
- Store metadata + summary so future runs can reference it without re-reading everything
