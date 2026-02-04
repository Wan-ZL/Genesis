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

## Phase 3: Self-Improvement Loop - 75% COMPLETE
- [x] Multi-agent architecture (Builder/Criticizer/Planner)
- [x] Automated verification gate
- [x] Performance tracking and metrics (Issue #7)
- [x] Streaming responses (Issue #6)
- [x] Conversation export/import (Issue #8)
- [ ] Auto-backlog generation from patterns
- [ ] PR-based evolution with review gates

## Phase 4: Production Hardening - CURRENT
- [ ] Error alerting and notifications (Issue #10)
- [ ] Backup and restore (Issue #11)
- [ ] Resource monitoring and limits (Issue #12)
- [ ] Log rotation and cleanup (Issue #13)
- [ ] Graceful degradation modes (Issue #14)

## Milestones
| Milestone | Target | Status |
|-----------|--------|--------|
| M1: First working iteration loop | Week 1 | COMPLETE |
| M2: Web UI + conversation | Week 2 | COMPLETE |
| M3: Multimodal input | Week 3 | COMPLETE |
| M4: Multi-agent system | Week 4 | COMPLETE |
| M5: Self-verification cycle | Week 5 | 75% COMPLETE |
| M6: Production hardening | Week 6 | STARTING |
