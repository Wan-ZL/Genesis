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

## Phase 3: Self-Improvement Loop - 85% COMPLETE

**Goal**: Enable the system to improve itself reliably.

- [x] Multi-agent architecture (Builder/Criticizer/Planner)
- [x] Issue-driven workflow with labels (9 labels created)
- [x] Architectural decision records (ADRs) - ADR-001 exists
- [x] Automated verification gate (Criticizer verified Issues #6-13)
- [x] Performance regression detection (Issue #7 - VERIFIED)
- [x] Streaming responses for better UX (Issue #6 - VERIFIED)
- [x] Conversation export/import (Issue #8 - VERIFIED)
- [x] Path consistency (Issue #9 - VERIFIED)
- [ ] Auto-backlog from bug patterns (deferred - no bugs found to trigger)
- [ ] PR-based evolution with review gates (deferred - current workflow effective)

**Success Criteria** - ACHIEVED:
- Builder cannot close issues (only Criticizer can) - WORKING
- All changes verified by actual API testing - WORKING (8 issues verified)
- Recurring bugs trigger tech-debt issues - NOT YET TESTED (zero bugs found by Criticizer)

**Note**: Remaining Phase 3 items deferred. The multi-agent system is working well enough that auto-backlog generation has not been needed (Criticizer found 0 bugs). PR-based evolution can be added when needed for team collaboration.

## Phase 4: Production Hardening - 80% COMPLETE

**Goal**: Make the system robust for continuous operation.

- [x] Error alerting and notifications (Issue #10 - VERIFIED)
- [x] Backup and restore procedures (Issue #11 - VERIFIED)
- [x] Resource monitoring and limits (Issue #12 - VERIFIED)
- [x] Log rotation and cleanup (Issue #13 - VERIFIED)
- [ ] Graceful degradation modes (Issue #14 - IN PROGRESS, ~60%)

**Remaining Work (Issue #14)**:
| Feature | Status | Notes |
|---------|--------|-------|
| API fallback | DONE | Claude/OpenAI automatic failover |
| Network detection | DONE | Offline state detection |
| UI status indicator | DONE | Color-coded banner |
| Rate limit queue | TODO | Infrastructure exists |
| Offline cached responses | TODO | Infrastructure exists |
| web_fetch caching | TODO | Not started |

## Phase 5: External Integration - PLANNED

**Goal**: Connect to external systems and enable remote access.

**Security Foundation**:
- [ ] Authentication layer for remote access (Issue #15)
- [ ] API key encryption at rest (Issue #17)

**Automation**:
- [ ] Scheduled task automation (Issue #16)

**Integrations** (not yet issues):
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
| M5: Self-verification cycle | Week 5 | COMPLETE |
| M5.1: Streaming responses | Week 5 | COMPLETE (#6 verified) |
| M5.2: Performance benchmarks | Week 5 | COMPLETE (#7 verified) |
| M5.3: Export/Import | Week 5 | COMPLETE (#8 verified) |
| M6: Production hardening | Week 6 | 80% COMPLETE |
| M6.1: Error alerting | Week 6 | COMPLETE (#10 verified) |
| M6.2: Backup/restore | Week 6 | COMPLETE (#11 verified) |
| M6.3: Resource monitoring | Week 6 | COMPLETE (#12 verified) |
| M6.4: Log rotation | Week 6 | COMPLETE (#13 verified) |
| M6.5: Graceful degradation | Week 6 | IN PROGRESS (#14) |

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
