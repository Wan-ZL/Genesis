# ADR-003: Phase 7 - "Proactive Companion"

## Status
ACCEPTED

## Date
2026-02-11

## Context

Phase 6 ("From Tool to Teammate") is complete. All 6 issues (#32-#37) were verified and closed. The Builder achieved 8 consecutive first-pass verifications. The product now has:
- Multi-conversation sidebar
- Dark mode with distinctive Genesis branding
- Persona system (backend complete, frontend missing)
- Keyboard shortcuts with quick switcher
- Markdown rendering with locally bundled dependencies
- 969 tests, 100% pass rate

However, two critical gaps remain:

### Gap 1: Frontend-Backend Disconnect
The Criticizer identified that backend capabilities significantly outpace the frontend. The persona system has a complete API but zero UI. Users cannot access features that already exist.

### Gap 2: No Proactive Intelligence
Genesis only responds -- it never initiates. Research shows:
- Proactive assistance increases engagement by 40%+ (CHI 2025)
- OpenClaw's Heartbeat Engine is one of its most loved features
- Calendar-based reminders are the #1 requested proactive feature
- "AI assistants should anticipate needs, not just respond" (2026 trend)

## Decision

Phase 7 will follow a "Close the Gap, Then Leap Forward" strategy:

**Part A: Close the frontend-backend gap (Issues #38, #39, #42, #43)**
- Persona switcher UI (#38) - CRITICAL
- Syntax highlighting (#39) - HIGH
- Cross-conversation search (#42) - MEDIUM
- Message actions (#43) - MEDIUM

**Part B: Proactive intelligence foundation (Issue #40)**
- Notification system with calendar reminders, daily briefing, health alerts

**Part C: Tech debt cleanup (Issue #41)**
- Encryption key management cleanup

### Priority Order
1. #38 (Persona UI) - Highest impact gap closure
2. #39 (Syntax highlighting) - Quick visual win
3. #40 (Proactive notifications) - The leap forward
4. #41 (Encryption cleanup) - Tech debt
5. #42 (Cross-conversation search) - Knowledge retrieval
6. #43 (Message actions) - Table-stakes interactions

## Consequences

### Positive
- Users can finally access all existing features
- Proactive notifications transform the product from reactive to anticipatory
- Syntax highlighting makes code assistance actually usable
- Message actions bring parity with competitors

### Negative
- 6 issues is a full phase of work
- Proactive notifications add system complexity
- Real-time notifications may require WebSocket infrastructure

### Risks
- Notification fatigue if proactive features are too aggressive
- WebSocket adds complexity to the server
- Syntax highlighting library adds to bundle size

## Alternatives Considered

1. **Multi-channel integration (WhatsApp/Telegram)**: Rejected for now. High complexity, requires gateway architecture. Better suited for Phase 8 after core experience is excellent.

2. **Long-term memory patterns**: Deferred. Requires more conversation data to learn from. Will be more valuable after proactive system is in place.

3. **Voice-first interaction improvements**: Deferred. Web Speech API already works. Voice is a secondary input mode for now.

4. **Mobile native app**: Rejected. Web UI with PWA would be sufficient first step. Native app premature.

## References
- Criticizer insights: criticizer_iteration/insights_for_planner.md
- Phase 6 research: planner_iteration/research/2026-02-07-ux-and-intelligence-gap.md
- Phase 7 research: planner_iteration/research/2026-02-11-proactive-intelligence-research.md
