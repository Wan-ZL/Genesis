# Backlog

> **Note**: Primary work tracking is via GitHub Issues. This backlog is for ideas not yet converted to issues.

## Active GitHub Issues (see `gh issue list`)

### Phase 5 (External Integration) - CONTINUING
- Issue #24: Code repository analysis tool (HIGH) - NEW - Self-improvement enabler
- Issue #22: Pydantic ConfigDict migration (LOW) - Tech Debt - Trivial

## Recently Completed (Phase 5)
- Issue #20: Local model fallback with Ollama - VERIFIED
- Issue #21: Calendar integration via CalDAV - VERIFIED
- Issue #23: Ollama status inconsistency fix - VERIFIED

## Completed Earlier (Phase 4)
- Issue #10: Error alerting and notifications - VERIFIED
- Issue #11: Backup and restore functionality - VERIFIED
- Issue #12: Resource monitoring and limits - VERIFIED
- Issue #13: Log rotation and cleanup - VERIFIED
- Issue #14: Graceful degradation modes - VERIFIED
- Issue #15: Authentication layer for remote access - VERIFIED
- Issue #16: Scheduled task automation - VERIFIED
- Issue #17: API key encryption at rest - VERIFIED
- Issue #18: Key rotation TypeError fix - VERIFIED
- Issue #19: Encrypted API key leak prevention - VERIFIED

## Pending User Action
- [ ] Activate Claude API (user needs to add ANTHROPIC_API_KEY)
- [ ] Configure valid OpenAI API key (current key appears invalid)
- [ ] Install Ollama for local model support (once Issue #20 is complete)

## Ideas (Not Yet Scoped as Issues)

### Phase 5 Extensions (External Integration)
- ~~Code repository analysis tool~~ - Issue #24 created
- Slack/Discord bot - Alternative interface
- Email summarization integration - Privacy considerations
- Task/todo integration - Overlaps with scheduler

### Phase 6 Candidates (Intelligence Enhancement)
- Context-aware tool selection improvements
- Long-term memory pattern learning
- Proactive suggestions based on context/time
- Multi-turn planning for complex tasks
- Knowledge base integration

## Completed (Phase 1-4)
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
- [x] Error alerting and notifications
- [x] Backup and restore
- [x] Resource monitoring and limits
- [x] Log rotation and cleanup
- [x] Graceful degradation modes
- [x] Authentication layer
- [x] Scheduled task automation
- [x] API key encryption at rest
