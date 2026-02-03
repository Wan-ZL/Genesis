# Backlog

## Priority: High
- [x] Create supervisor service for 24/7 assistant runtime (launchd/systemd)
- [ ] Activate Claude API (user needs to add ANTHROPIC_API_KEY)
- [x] Add comprehensive tests for chat API

## Priority: Medium
- [~] Tool registry system ← **FOUNDATION DONE** (next: integrate with chat API)
- [ ] Eval framework for LLM outputs
- [x] Add health check endpoint for monitoring
- [ ] Error recovery and auto-restart

## Priority: Low
- [ ] Metrics dashboard
- [ ] CI integration for automated tests
- [ ] Mobile-friendly UI improvements
- [ ] Voice input support

## Completed (for reference)
- [x] Web UI: basic chat interface
- [x] Web UI: status panel showing agent/state.md
- [x] Multimodal: image upload + storage
- [x] Multimodal: PDF support via Claude document type
- [x] Conversation persistence (SQLite)
- [x] Claude API integration code (needs API key)
- [x] Set up basic test framework (pytest)
- [x] Hooks system for Claude Code iteration loop

## Ideas (Unscoped)
- Integration with calendar/tasks
- Automated PR review suggestions
- Real-time streaming responses
- Conversation export/import
