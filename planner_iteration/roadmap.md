# Genesis Roadmap

> **Owned by: Planner**
> Last updated: 2026-02-11 (Phase 8 planning)

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
- [x] Architectural decision records (ADRs) - 3 ADRs
- [x] Automated verification gate (Criticizer verified 43 issues)
- [x] Auto-backlog from bug patterns - PROVEN WORKING

**Outcome**: Fully autonomous development loop with independent verification.

## Phase 4: Production Hardening - COMPLETE

**Goal**: Make the system robust for continuous operation.

- [x] Error alerting and notifications (#10)
- [x] Backup and restore (#11)
- [x] Resource monitoring and limits (#12)
- [x] Log rotation and cleanup (#13)
- [x] Graceful degradation modes (#14)
- [x] Authentication layer (#15)
- [x] Scheduled task automation (#16)
- [x] API key encryption at rest (#17, #18, #19)

**Outcome**: Robust 24/7 operation with monitoring, alerting, backup, and security.

## Phase 5: External Integration - COMPLETE

**Goal**: Connect to external systems and enable advanced automation.

- [x] Local model fallback with Ollama (#20, #23)
- [x] Calendar integration via CalDAV (#21)
- [x] Code repository analysis (#24)
- [x] Tech debt cleanup (#22, #25, #26, #27, #28, #29)

**Outcome**: Full external integration capabilities with 800+ tests.

## Phase 6: From Tool to Teammate - COMPLETE

**Goal**: Transform Genesis from a capable tool into a product users love.

- [x] Conversation sidebar with multi-conversation support (#32)
- [x] Dark mode and UI visual refresh (#33)
- [x] Custom system prompt and persona customization (#34)
- [x] Bundle markdown libraries locally (#35)
- [x] Keyboard shortcuts for power users (#36)
- [x] Settings test fix (#37)

**Outcome**: Polished power-user experience with 969 tests. 8 consecutive first-pass verifications.

## Phase 7: Proactive Companion - COMPLETE

**Goal**: Close frontend-backend gap, add proactive intelligence.

- [x] Persona switcher UI in chat interface (#38)
- [x] Code syntax highlighting with highlight.js (#39)
- [x] Proactive notification system / Heartbeat Engine (#40)
- [x] Encryption key management cleanup (#41)
- [x] Conversation search across all conversations (#42)
- [x] Message actions: copy, edit, regenerate, delete (#43)

**Outcome**: Engaging proactive assistant with 1113+ tests. 11 consecutive first-pass verifications. Phase completed in a single day.

## Phase 8: Always-On Partner - IN PROGRESS

**Goal**: Make Genesis accessible everywhere and deeply integrated into daily life.

**Theme**: "Be Everywhere, Know Me, Do More"

**Decision**: ADR-004 (see `planner_iteration/decisions/ADR-004-phase8-always-on-partner.md`)

**Pillar 1: Be Everywhere (Accessibility)**
- [ ] PWA Support: installable, push notifications, offline access (#44) - CRITICAL
- [ ] Telegram Bot Gateway for multi-channel messaging (#46) - HIGH

**Pillar 2: Know Me (Long-Term Memory)**
- [ ] Long-term memory: user preference extraction and recall (#45) - CRITICAL
- [ ] User profile and context system (#47) - HIGH

**Pillar 3: Do More (Agentic Capability)**
- [ ] Browser automation tool (#48) - MEDIUM
- [ ] File management tool (#49) - MEDIUM

**Dependencies**: #47 depends on #45 (user profile aggregates from extracted facts)

## Phase 9: Intelligent Ecosystem - PROPOSED

**Goal**: Create a self-sustaining AI ecosystem that grows in capability.

**Potential Features**:
- [ ] Email integration (OAuth2, summarization, drafting)
- [ ] WhatsApp gateway (via Baileys or official Cloud API)
- [ ] Smart scheduling and task management
- [ ] Voice improvements (whisper-based transcription)
- [ ] Plugin system for community extensions
- [ ] Integration tests across all features
- [ ] Vector database for semantic memory search

**Dependencies**: Requires Phase 8 memory system and multi-channel pattern proven.

## Milestones

| Milestone | Target | Status |
|-----------|--------|--------|
| M1: First iteration loop | Week 1 | COMPLETE |
| M2: Web UI + conversation | Week 2 | COMPLETE |
| M3: Multimodal input | Week 3 | COMPLETE |
| M4: Multi-agent system | Week 4 | COMPLETE |
| M5: Self-verification cycle | Week 5 | COMPLETE |
| M6: Production hardening | Week 6 | COMPLETE |
| M7: External integrations | Week 7 | COMPLETE |
| M8: From Tool to Teammate | Week 8 | COMPLETE |
| M9: Proactive Companion | Week 9 | COMPLETE |
| M9.1: Persona switcher UI | Week 9 | COMPLETE (#38) |
| M9.2: Syntax highlighting | Week 9 | COMPLETE (#39) |
| M9.3: Proactive notifications | Week 9 | COMPLETE (#40) |
| M9.4: Encryption cleanup | Week 9 | COMPLETE (#41) |
| M9.5: Cross-conversation search | Week 9 | COMPLETE (#42) |
| M9.6: Message actions | Week 9 | COMPLETE (#43) |
| M10: Always-On Partner | Week 10-11 | IN PROGRESS |
| M10.1: PWA Support | Week 10 | PENDING (#44) |
| M10.2: Long-term memory | Week 10 | PENDING (#45) |
| M10.3: Telegram bot | Week 10-11 | PENDING (#46) |
| M10.4: User profile | Week 11 | PENDING (#47) |
| M10.5: Browser automation | Week 11 | PENDING (#48) |
| M10.6: File management | Week 11 | PENDING (#49) |
| M11: Intelligent Ecosystem | Week 12+ | PROPOSED |

## Statistics

| Metric | Value |
|--------|-------|
| Total issues created | 49 |
| Issues verified and closed | 43 |
| Issues open | 6 |
| Bugs found by Criticizer | 3 |
| Total tests | 1113+ |
| Service modules | 25+ |
| Phases completed | 7 of 9 |
| Builder first-pass rate | 100% (11/11 consecutive) |
| ADRs written | 4 |
| Research documents | 4 |

## Principles

1. **Incremental progress**: Small, verified changes over big rewrites
2. **Trust but verify**: Builder implements, Criticizer validates
3. **Documentation as memory**: Everything persisted in repo
4. **Quality over speed**: No shortcuts on testing
5. **User value first**: Features that matter to real use
6. **Presence over features**: Being accessible is more important than having more features

## Anti-Patterns to Avoid

1. **Self-verification**: Builder should not verify its own work
2. **Scope creep**: Stick to acceptance criteria
3. **Tech debt accumulation**: Address patterns, not just symptoms
4. **Over-engineering**: Simple solutions first
5. **Ignoring failures**: Every bug is a learning opportunity
6. **Feature hoarding**: Building features nobody uses because they cannot find them

## Key Learning: Multi-Agent Validation

The multi-agent system has proven its value multiple times. 43 issues verified independently, with 3 bugs caught that passed all unit tests. The Builder has achieved 11 consecutive first-pass verifications, demonstrating the system's maturity.

## Current Product Capabilities

The AI Assistant now supports:
- **Communication**: Web UI, CLI, API
- **AI Providers**: Claude, OpenAI, Ollama (local)
- **Tools**: datetime, calculate, web_fetch, shell, calendar (5 events tools), repository analysis
- **Security**: Authentication, API key encryption, permission levels, path validation
- **Reliability**: Graceful degradation, backup/restore, monitoring, alerts, error deduplication
- **Operations**: Log rotation, resource limits, scheduled tasks
- **Data**: SQLite persistence, conversation export/import, cross-conversation search
- **UX**: Dark mode, personas, syntax highlighting, message actions, keyboard shortcuts
- **Proactive**: Calendar reminders, daily briefing, system health monitoring, quiet hours
