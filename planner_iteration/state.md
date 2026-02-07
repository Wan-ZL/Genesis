# Planner State

## Last Review
2026-02-07 (Phase 6 strategic planning)

## Current Phase
Phase 6: From Tool to Teammate - STARTING

## Product Health
- Would users love this? **Not yet.** The backend is excellent but the UX is generic and lacks personality.
- Distance from vision? **Medium.** We have the foundation but the experience does not match "everyone loves it, everyone depends on it."

## Phase Progress

### Phase 1-5: COMPLETE
All infrastructure, core runtime, self-improvement loop, production hardening, and external integrations are done. 31 issues resolved. 800+ tests passing.

### Phase 6: From Tool to Teammate - IN PROGRESS
Theme: Transform Genesis from a capable tool into a product users love.

## Priority Queue

1. **#32** - Conversation sidebar with multi-conversation support - priority-critical
   - Most impactful UX change. Single infinite conversation is an anti-pattern.
   - Effort: High (backend re-exposure + frontend sidebar + mobile drawer)

2. **#33** - Dark mode and UI visual refresh - priority-high
   - Distinctive identity, modern look, comfortable for extended use
   - Effort: Medium (CSS custom properties, theme toggle, color palette)

3. **#34** - Custom system prompt and persona customization - priority-high
   - Core self-hosted differentiator. Users want control over AI behavior.
   - Effort: Medium (settings field + persona templates + per-conversation override)

4. **#35** - Bundle markdown libraries locally - priority-medium
   - Product integrity issue. Local-first must mean local-first.
   - Effort: Low (download files, update paths)

5. **#36** - Keyboard shortcuts for power users - priority-medium
   - Professional feel. Depends on #32 for Cmd+N and Cmd+K.
   - Effort: Low-Medium

6. **#37** - Fix pre-existing settings test failure - priority-low
   - Quality hygiene. 46/47 is not acceptable.
   - Effort: Trivial

## Recent Decisions
- **ADR-002 ACCEPTED**: Phase 6 theme "From Tool to Teammate" -- focus on UX polish, conversation management, and customization
- **Deferred**: Slack/Discord bot, email summarization, proactive suggestions -- these are Phase 7 candidates
- **Rejected for now**: Mobile native app, more backend integrations -- premature without UX excellence

## Research Insights
- Every successful AI assistant in 2026 has: multi-conversation, dark mode, customizable persona
- Self-hosted assistant users specifically value: privacy, offline capability, unlimited customization
- "The right AI assistants should feel like teammates -- not another tool to manage"
- Proactive intelligence (anticipating user needs) is the next frontier, but requires stable multi-conversation model first
- See: planner_iteration/research/2026-02-07-ux-and-intelligence-gap.md

## Observations

### Multi-Agent System
- Criticizer reports: Builder work quality is improving (100% first-pass verification rate)
- System is healthy, no architectural debt
- SQLite concurrency fully resolved
- 800+ tests, all critical paths covered

### Quality Smell
- 1 pre-existing test failure in settings tests has been carried across 3+ issues without being addressed
- Tracked as Issue #37

## Recommendations for Builder
1. **Start with #32 (Conversation sidebar)** - This is the highest-impact change
2. **Then #35 (Bundle CDN deps)** - Quick win, product integrity fix
3. **Then #33 (Dark mode)** - Builds on sidebar work for consistent theming
4. Priority order: #32 > #35 > #33 > #34 > #36 > #37

## Next Review
- After Issue #32 is verified
- Or in 3 days if progress is slow
- Maximum 1 week between reviews
