# Roadmap

> **Note**: This is the Builder's reference copy. The authoritative roadmap is at `planner_iteration/roadmap.md`

## Phase 1: Bootstrap - COMPLETE
- [x] Define repo structure and memory rules
- [x] Create minimal web UI for interaction
- [x] Set up hooks system for iteration loop
- [x] Implement supervisor service for 24/7 operation

## Phase 2: Core Runtime - COMPLETE
- [x] Implement conversation persistence (SQLite)
- [x] Add multimodal support (images, PDFs)
- [x] Claude API integration
- [x] Create tool registry and first tools (datetime, calculate, web_fetch)
- [x] Add basic evals for assistant behavior
- [x] Supervisor service for process management

## Phase 3: Self-Improvement Loop - COMPLETE
- [x] Multi-agent architecture (Builder/Criticizer/Planner)
- [x] Automated verification gate
- [x] Performance tracking and metrics (Issue #7)
- [x] Streaming responses (Issue #6)
- [x] Conversation export/import (Issue #8)
- [x] Auto-backlog from bug patterns (Issues #18, #19 created by Criticizer)
- [ ] PR-based evolution with review gates (deferred)

## Phase 4: Production Hardening - COMPLETE
- [x] Error alerting and notifications (Issue #10)
- [x] Backup and restore (Issue #11)
- [x] Resource monitoring and limits (Issue #12)
- [x] Log rotation and cleanup (Issue #13)
- [x] Graceful degradation modes (Issue #14)
- [x] Authentication layer (Issue #15)
- [x] Scheduled task automation (Issue #16)
- [x] API key encryption at rest (Issue #17)
- [x] Bug fixes: #18, #19

## Phase 5: External Integration - READY TO START
- [ ] Local model fallback (ollama) - HIGH PRIORITY
- [ ] Calendar integration - MEDIUM PRIORITY
- [ ] Code repository analysis - MEDIUM PRIORITY
- [ ] Slack/Discord bot - MEDIUM PRIORITY

## Milestones
| Milestone | Target | Status |
|-----------|--------|--------|
| M1: First working iteration loop | Week 1 | COMPLETE |
| M2: Web UI + conversation | Week 2 | COMPLETE |
| M3: Multimodal input | Week 3 | COMPLETE |
| M4: Multi-agent system | Week 4 | COMPLETE |
| M5: Self-verification cycle | Week 5 | COMPLETE |
| M6: Production hardening | Week 6 | COMPLETE |
| M7: External integrations | Week 7+ | READY TO START |
