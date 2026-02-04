# Genesis Roadmap

> **Owned by: Planner**
> Last updated: 2026-02-04 (evening)

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

## Phase 3: Self-Improvement Loop - COMPLETE

**Goal**: Enable the system to improve itself reliably.

- [x] Multi-agent architecture (Builder/Criticizer/Planner)
- [x] Issue-driven workflow with labels (9 labels created)
- [x] Architectural decision records (ADRs) - ADR-001 exists
- [x] Automated verification gate (Criticizer verified Issues #6-19)
- [x] Performance regression detection (Issue #7)
- [x] Streaming responses for better UX (Issue #6)
- [x] Conversation export/import (Issue #8)
- [x] Path consistency (Issue #9)
- [x] Auto-backlog from bug patterns - PROVEN WORKING (Issues #18, #19 created by Criticizer)
- [ ] PR-based evolution with review gates (deferred - current workflow effective)

**Success Criteria** - ALL ACHIEVED:
- Builder cannot close issues (only Criticizer can) - WORKING
- All changes verified by actual API testing - WORKING (14 issues verified)
- Recurring bugs trigger tech-debt issues - WORKING (2 bugs found by Criticizer)

**Key Learning**: The multi-agent system proved its value by catching 2 bugs in Issue #17 that passed all unit tests but failed real API testing.

## Phase 4: Production Hardening - COMPLETE

**Goal**: Make the system robust for continuous operation.

- [x] Error alerting and notifications (Issue #10 - VERIFIED)
- [x] Backup and restore procedures (Issue #11 - VERIFIED)
- [x] Resource monitoring and limits (Issue #12 - VERIFIED)
- [x] Log rotation and cleanup (Issue #13 - VERIFIED)
- [x] Graceful degradation modes (Issue #14 - VERIFIED)
- [x] Authentication layer (Issue #15 - VERIFIED)
- [x] Scheduled task automation (Issue #16 - VERIFIED)
- [x] API key encryption at rest (Issue #17 - VERIFIED)
- [x] Bug fix: Key rotation TypeError (Issue #18 - VERIFIED)
- [x] Bug fix: Encrypted API key leak prevention (Issue #19 - VERIFIED)

**Outcome**: Robust 24/7 operation with monitoring, alerting, backup, and security features. 675 tests passing.

## Phase 5: External Integration - NEAR COMPLETE

**Goal**: Connect to external systems and enable advanced automation.

**Security Foundation** (complete):
- [x] Authentication layer for remote access (Issue #15)
- [x] API key encryption at rest (Issue #17)
- [x] Scheduled task automation (Issue #16)

**Completed Integrations**:
- [x] Local model fallback with Ollama (Issue #20 - VERIFIED)
- [x] Calendar integration via CalDAV (Issue #21 - VERIFIED)
- [x] Bug fix: Ollama status consistency (Issue #23 - VERIFIED)

**In Progress**:
- [ ] Code repository analysis (Issue #24 - HIGH, self-improvement enabler)
- [ ] Pydantic ConfigDict migration (Issue #22 - LOW, trivial tech debt)

**Remaining Integration Candidates** (not yet created as issues):

| Integration | Priority | Value | Effort | Notes |
|-------------|----------|-------|--------|-------|
| Slack/Discord bot | MEDIUM | Medium | Medium | Alternative interface |
| Email summarization | MEDIUM | Medium | High | Privacy considerations |
| Task/todo integration | LOW | Medium | Low | Overlaps with scheduler |

## Phase 6: Intelligence Enhancement - PROPOSED

**Goal**: Make the assistant smarter and more proactive.

**Potential Features**:
- [ ] Context-aware tool selection - Improve accuracy of tool suggestions
- [ ] Long-term memory patterns - Learn user preferences over time
- [ ] Proactive suggestions - Anticipate needs based on context/time
- [ ] Multi-turn planning - Handle complex multi-step tasks autonomously
- [ ] Conversation summarization improvements - Better context compression
- [ ] Knowledge base integration - Store and retrieve domain knowledge

**Dependencies**: Requires stable Phase 5 foundation (complete)

## Milestones

| Milestone | Target | Status |
|-----------|--------|--------|
| M1: First iteration loop | Week 1 | COMPLETE |
| M2: Web UI + conversation | Week 2 | COMPLETE |
| M3: Multimodal input | Week 3 | COMPLETE |
| M4: Multi-agent system | Week 4 | COMPLETE |
| M5: Self-verification cycle | Week 5 | COMPLETE |
| M6: Production hardening | Week 6 | COMPLETE |
| M6.1: Error alerting | Week 6 | COMPLETE (#10) |
| M6.2: Backup/restore | Week 6 | COMPLETE (#11) |
| M6.3: Resource monitoring | Week 6 | COMPLETE (#12) |
| M6.4: Log rotation | Week 6 | COMPLETE (#13) |
| M6.5: Graceful degradation | Week 6 | COMPLETE (#14) |
| M6.6: Authentication | Week 6 | COMPLETE (#15) |
| M6.7: Scheduled tasks | Week 6 | COMPLETE (#16) |
| M6.8: Encryption + bug fixes | Week 6 | COMPLETE (#17, #18, #19) |
| M7: External integrations | Week 7 | NEAR COMPLETE |
| M7.1: Ollama integration | Week 7 | COMPLETE (#20, #23) |
| M7.2: Calendar integration | Week 7 | COMPLETE (#21) |
| M7.3: Code repository analysis | Week 7 | IN PROGRESS (#24) |
| M7.4: Tech debt cleanup | Week 7 | PENDING (#22) |
| M8: Intelligence enhancement | Week 8+ | PROPOSED |

## Statistics

| Metric | Value |
|--------|-------|
| Total issues created | 24 |
| Issues verified and closed | 22 |
| Issues open | 2 |
| Bugs found by Criticizer | 3 |
| Total tests | 745 |
| Service modules | 17+ |
| Phases completed | 4.9 of 5 |

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

## Key Learning: Multi-Agent Validation

The multi-agent system has proven its value multiple times:

**Issue #17 (API key encryption)** - passed all 667 unit tests but Criticizer found 2 bugs:
1. **#19 (Critical)**: Silent decryption failure causes encrypted keys to be sent to external APIs
2. **#18 (Low)**: Key rotation has TypeError in edge case

**Issue #20 (Ollama integration)** - Criticizer found during verification:
3. **#23 (Medium)**: Degradation service showed Ollama as available when not running

All 3 bugs were fixed by Builder and verified by Criticizer. This proves the value of independent verification - unit tests alone are not sufficient for quality assurance.

## Current Project Capabilities

The AI Assistant now supports:
- **Communication**: Web UI, CLI, API
- **AI Providers**: Claude, OpenAI, Ollama (local)
- **Tools**: datetime, calculate, web_fetch, shell, calendar (5 events tools)
- **Security**: Authentication, API key encryption, permission levels
- **Reliability**: Graceful degradation, backup/restore, monitoring, alerts
- **Operations**: Log rotation, resource limits, scheduled tasks
- **Data**: SQLite persistence, conversation export/import, message search
