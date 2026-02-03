# Backlog

## Priority: High
- [x] Create supervisor service for 24/7 assistant runtime (launchd/systemd)
- [ ] Activate Claude API (user needs to add ANTHROPIC_API_KEY)
- [x] Add comprehensive tests for chat API

## Priority: Medium
- [x] Tool registry system ← **COMPLETE** (registry, datetime, calculate, web_fetch tools)
- [x] Eval framework for LLM outputs ← **COMPLETE** (framework, 6 cases, SQLite storage, 26 tests)
- [x] Add health check endpoint for monitoring
- [x] Error recovery and auto-restart ← **COMPLETE** (retry logic + launchd auto-restart)
- [x] CLI runner for evals (`python -m evals`) ← **COMPLETE**

## Priority: Low
- [x] Metrics dashboard ← **COMPLETE** (backend API + UI panel with auto-refresh)
- [x] CI integration for automated tests ← **COMPLETE** (GitHub Actions workflow)
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
