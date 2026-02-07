# ADR-002: Phase 6 Direction - "From Tool to Teammate"

## Status
ACCEPTED

## Date
2026-02-07

## Context

Genesis has completed Phases 1-5:
- Phase 1: Bootstrap
- Phase 2: Core Runtime
- Phase 3: Self-Improvement Loop
- Phase 4: Production Hardening
- Phase 5: External Integration

The system is technically solid: 800+ tests, 31 issues resolved, robust backend with security, monitoring, and multiple AI provider support.

However, the product still feels like a technical demo rather than something a user would love. The UI is generic, there is no conversation management, and the experience lacks personality and polish.

## Decision

Phase 6 will focus on transforming Genesis from a capable tool into a product that feels like an intelligent teammate. The theme is "From Tool to Teammate."

**Phase 6 priority order:**

1. **Conversation sidebar** (#32) - CRITICAL - Multi-conversation support with sidebar UI
2. **Dark mode + visual refresh** (#33) - HIGH - Distinctive identity, modern look
3. **System prompt customization** (#34) - HIGH - Core self-hosted differentiator
4. **Bundle CDN dependencies** (#35) - MEDIUM - Product integrity (local-first promise)
5. **Keyboard shortcuts** (#36) - MEDIUM - Power user experience
6. **Fix pre-existing test** (#37) - LOW - Quality hygiene

**Deferred from Phase 6:**
- Slack/Discord bot (Phase 7 - after core UX is polished)
- Email summarization (Phase 7 - privacy complexity)
- Proactive suggestions (Phase 7 - requires stable conversation model first)
- Task/todo integration (Phase 7 - overlaps with scheduler)

## Rationale

1. **Research-driven**: Competitive analysis shows every successful AI assistant in 2026 has polished UX, conversation management, and customization.

2. **Self-hosted differentiation**: Custom system prompts and offline-first are the core reasons to self-host. We need to deliver on those promises.

3. **Foundation before intelligence**: Proactive suggestions and advanced intelligence features need a stable multi-conversation model to build on. Polish the container before filling it with magic.

4. **User value ordering**: Conversation sidebar has the highest impact because it changes the fundamental interaction model. Dark mode has high impact because it affects every moment of use.

## Consequences

- Builder will focus on UX/frontend work more than backend in Phase 6
- CSS will undergo significant restructuring (CSS custom properties for theming)
- Database may need conversation title column additions
- The "single infinite conversation" model will be retired

## Alternatives Considered

### A: Continue with more backend integrations (Phase 5 extension)
Rejected. The backend is already robust. Adding more integrations without fixing the UX would make the product more capable but not more lovable.

### B: Jump to proactive intelligence
Rejected. Proactive features need a stable multi-conversation model. Building intelligence on top of a single-conversation model would require rework.

### C: Focus on mobile app
Rejected. Too early. The web UI is the primary interface and needs to be excellent before branching to native apps.
