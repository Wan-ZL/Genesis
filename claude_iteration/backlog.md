# Backlog

> **Note**: Primary work tracking is via GitHub Issues. This backlog is for ideas not yet converted to issues.

## Active GitHub Issues (see `gh issue list`)

### Phase 4 (Production Hardening)
- Issue #14: Graceful degradation modes (MEDIUM) - IN PROGRESS

### Phase 5 (External Integration) - NEW
- Issue #15: Authentication layer for remote access (MEDIUM)
- Issue #16: Scheduled task automation (MEDIUM)
- Issue #17: API key encryption at rest (MEDIUM)

## Recently Completed (Phase 4)
- Issue #10: Error alerting and notifications - VERIFIED
- Issue #11: Backup and restore functionality - VERIFIED
- Issue #12: Resource monitoring and limits - VERIFIED
- Issue #13: Log rotation and cleanup - VERIFIED

## Pending User Action
- [ ] Activate Claude API (user needs to add ANTHROPIC_API_KEY)
- [ ] Configure valid OpenAI API key (current key appears invalid)

## Ideas (Not Yet Scoped as Issues)
- Integration with calendar/tasks
- Automated PR review suggestions
- Email summarization integration
- Slack/Discord bot
- Local model fallback (ollama) for offline mode
- Authentication layer for remote access
- Code repository analysis tool

## Completed (Phase 1-3)
- [x] Repo structure and memory rules
- [x] Web UI with chat interface
- [x] Hooks system for iteration loop
- [x] Supervisor service for 24/7 operation
- [x] Conversation persistence (SQLite)
- [x] Multimodal support (images, PDFs)
- [x] Claude/OpenAI API integration
- [x] Tool registry (datetime, calculate, web_fetch, shell)
- [x] Eval framework with CLI runner
- [x] Health check endpoint
- [x] Retry logic with exponential backoff
- [x] Metrics dashboard with auto-refresh
- [x] CI integration (GitHub Actions)
- [x] Mobile-friendly UI
- [x] Voice input support
- [x] Settings page with persistence
- [x] Permission system (4 levels)
- [x] Capability discovery (23+ tools)
- [x] Message search and auto-summarization
- [x] Streaming responses (SSE)
- [x] Performance benchmarks
- [x] Conversation export/import
- [x] Path consistency fix
