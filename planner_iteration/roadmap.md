# Genesis Roadmap

> **Owned by: Planner**
> Last updated: 2026-02-04

## Vision

Genesis is a self-evolving AI development system where AI agents collaborate to build and improve software. The system consists of:
- **Builder**: Implements features and fixes bugs
- **Criticizer**: Verifies completions and discovers bugs
- **Planner**: Sets direction and priorities

## Phase 1: Bootstrap - COMPLETE

**Goal**: Establish the foundation for automated development.

- [x] Define repo structure and memory rules
- [x] Create minimal web UI for interaction
- [x] Set up hooks system for iteration loop
- [x] Implement supervisor service for 24/7 operation

**Outcome**: Working iteration loop with persistent context.

## Phase 2: Core Runtime - COMPLETE

**Goal**: Build a functional AI assistant product.

- [x] Conversation persistence (SQLite)
- [x] Multimodal support (images, PDFs)
- [x] Claude/OpenAI API integration
- [x] Tool registry system (datetime, calculate, web_fetch, shell)
- [x] Eval framework for behavior testing
- [x] Supervisor service (24/7 operation)
- [x] Permission system (4 levels)
- [x] Capability discovery (23+ CLI tools)
- [x] Settings persistence
- [x] Message search and auto-summarization
- [x] Metrics dashboard

**Outcome**: Fully functional AI assistant with 328 passing tests.

## Phase 3: Self-Improvement Loop - 75% COMPLETE

**Goal**: Enable the system to improve itself reliably.

- [x] Multi-agent architecture (Builder/Criticizer/Planner)
- [x] Issue-driven workflow with labels (8 labels created)
- [x] Architectural decision records (ADRs) - ADR-001 exists
- [x] Automated verification gate (Criticizer verified Issues #6-9)
- [x] Performance regression detection (Issue #7 - VERIFIED)
- [x] Streaming responses for better UX (Issue #6 - VERIFIED)
- [x] Conversation export/import (Issue #8 - VERIFIED)
- [x] Path consistency (Issue #9 - VERIFIED)
- [ ] Auto-backlog from bug patterns
- [ ] PR-based evolution with review gates

**Success Criteria** - ACHIEVED:
- Builder cannot close issues (only Criticizer can) - WORKING
- All changes verified by actual API testing - WORKING (4 issues verified)
- Recurring bugs trigger tech-debt issues - NOT YET TESTED (no bugs found)

## Phase 4: Production Hardening - CURRENT

**Goal**: Make the system robust for continuous operation.

- [ ] Error alerting and notifications (Issue #10 - HIGH)
- [ ] Backup and restore procedures (Issue #11 - HIGH)
- [ ] Resource monitoring and limits (Issue #12 - MEDIUM)
- [ ] Log rotation and cleanup (Issue #13 - MEDIUM)
- [ ] Graceful degradation modes (Issue #14 - MEDIUM)

**Active Issues**:
| Issue | Title | Priority |
|-------|-------|----------|
| #10 | Error alerting and notifications | High |
| #11 | Backup and restore functionality | High |
| #12 | Resource monitoring and limits | Medium |
| #13 | Log rotation and cleanup | Medium |
| #14 | Graceful degradation modes | Medium |

## Phase 5: External Integration

**Goal**: Connect to external systems for real utility.

- [ ] Calendar integration
- [ ] Task/todo integration
- [ ] Email summarization
- [ ] Code repository analysis
- [ ] Slack/Discord bot

## Milestones

| Milestone | Target | Status |
|-----------|--------|--------|
| M1: First iteration loop | Week 1 | COMPLETE |
| M2: Web UI + conversation | Week 2 | COMPLETE |
| M3: Multimodal input | Week 3 | COMPLETE |
| M4: Multi-agent system | Week 4 | COMPLETE |
| M5: Self-verification cycle | Week 5 | 75% COMPLETE |
| M5.1: Streaming responses | Week 5 | COMPLETE (#6 verified) |
| M5.2: Performance benchmarks | Week 5 | COMPLETE (#7 verified) |
| M5.3: Export/Import | Week 5 | COMPLETE (#8 verified) |
| M6: Production hardening | Week 6 | STARTING (5 issues created) |

## Principles

1. **Incremental progress**: Small, verified changes over big rewrites
2. **Trust but verify**: Builder implements, Criticizer validates
3. **Documentation as memory**: Everything persisted in repo
4. **Quality over speed**: No shortcuts on testing
5. **User value first**: Features that matter to real use

## Anti-Patterns to Avoid

1. **Self-verification**: Builder should not verify its own work
2. **Scope creep**: Stick to acceptance criteria
3. **Tech debt accumulation**: Address patterns, not just symptoms
4. **Over-engineering**: Simple solutions first
5. **Ignoring failures**: Every bug is a learning opportunity
