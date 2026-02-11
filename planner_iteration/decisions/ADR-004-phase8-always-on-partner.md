# ADR-004: Phase 8 - "Always-On Partner"

## Status
ACCEPTED

## Date
2026-02-11

## Context

Phase 7 ("Proactive Companion") is complete. All 6 issues (#38-#43) are verified and closed. The product now has:
- Persona system with full UI (create, edit, switch, delete)
- Code syntax highlighting with 34+ languages and copy buttons
- Proactive notification system (calendar reminders, daily briefing, system health)
- Message actions (copy, edit, regenerate, delete)
- Cross-conversation search integrated into Quick Switcher (Cmd+K)
- Encryption key management with CLI tools and error deduplication
- 1113+ tests, 100% pass rate
- 11 consecutive first-pass Builder verifications

The product is feature-complete for a single-user, single-device, browser-based AI assistant. However, this limits Genesis to being used only when the user actively navigates to localhost:8080 on their Mac mini.

### The Core Problem

Genesis is invisible. Users must *seek it out*. This is the fundamental barrier between a tool and a partner.

Three forces drive this:

1. **Access friction**: Browser-only, single-device, no mobile. Users cannot interact from their phone, another computer, or when away.

2. **No accumulated intelligence**: Genesis stores conversations but does not LEARN from them. It does not build a model of user preferences, habits, or patterns. Every new conversation starts from zero context.

3. **No workflow presence**: Genesis lives in its own tab. It is not present where users already spend time (messaging apps, system tray).

### Market Research (2026-02-11)

- OpenClaw (171k GitHub stars) proves massive demand for self-hosted, multi-channel AI assistants
- Mem0's memory layer achieves 26% higher accuracy than OpenAI's memory by combining vector search + graph relationships
- PWAs eliminate the need for native apps while enabling offline access, push notifications, and home screen installation
- Telegram bot setup takes 15-20 minutes with frameworks like python-telegram-bot
- Users switch from ChatGPT primarily due to: privacy concerns, lack of integration with existing workflows, and inability to customize

## Decision

Phase 8: "Always-On Partner" will focus on three pillars:

### Pillar 1: Be Everywhere (Accessibility)

**Goal**: Users can reach Genesis from any device, anywhere.

| Issue | Feature | Priority | Effort |
|-------|---------|----------|--------|
| #44 | PWA Support (service worker, manifest, installable) | CRITICAL | Medium |
| #45 | Telegram Bot Gateway | HIGH | Medium |

**PWA** makes Genesis installable on any device with a browser, enables push notifications and offline access, and eliminates the "just another browser tab" problem. This is the lowest-friction path to mobile access.

**Telegram Bot** puts Genesis where users already are. Telegram is chosen over WhatsApp because: open API with no business account needed, free with no message limits, supports rich formatting (markdown, buttons, images), and has a thriving bot ecosystem.

### Pillar 2: Know Me (Long-Term Memory)

**Goal**: Genesis learns from every interaction and becomes more valuable over time.

| Issue | Feature | Priority | Effort |
|-------|---------|----------|--------|
| #46 | Long-term memory: user preference extraction and recall | CRITICAL | High |
| #47 | User profile and context system | HIGH | Medium |

**Long-term memory** extracts facts, preferences, and patterns from conversations and stores them in a structured knowledge graph. When the user says "I prefer dark roast coffee" in conversation 5, Genesis remembers this in conversation 500. This creates massive switching costs -- the longer you use Genesis, the more it knows you, and the harder it is to leave.

**User profile** aggregates extracted preferences into a coherent model of who the user is -- their work, interests, schedule patterns, communication style, and preferences. This profile informs every response.

### Pillar 3: Do More (Agentic Capability)

**Goal**: Genesis can execute multi-step tasks, not just discuss them.

| Issue | Feature | Priority | Effort |
|-------|---------|----------|--------|
| #48 | Browser automation tool (web scraping, form filling) | MEDIUM | High |
| #49 | File management tool (organize, rename, search local files) | MEDIUM | Medium |

These tools transform Genesis from "AI that talks" to "AI that does." They require SYSTEM or FULL permission level, which the existing permission system supports.

### Priority Order
1. #44 (PWA) - Highest ROI. Unlocks mobile, push notifications, installability with relatively low effort.
2. #46 (Long-term memory) - The biggest differentiator. Creates stickiness and accumulated value.
3. #45 (Telegram bot) - Multi-channel presence. Puts Genesis in the user's pocket.
4. #47 (User profile) - Builds on #46 to create a coherent user model.
5. #48 (Browser automation) - Expands what Genesis can DO.
6. #49 (File management) - Practical local-first capability.

## Consequences

### Positive
- Genesis becomes accessible from any device (PWA)
- Genesis gets smarter the more you use it (long-term memory)
- Genesis is present where users already are (Telegram)
- Genesis can execute real tasks (browser, files)
- Massive switching costs from accumulated personalization

### Negative
- 6 issues is a full phase of work
- Long-term memory adds significant architectural complexity
- Telegram gateway introduces external dependency
- Browser automation has security implications

### Risks
- PWA service worker caching can cause stale content issues
- Long-term memory extraction quality depends on LLM reliability
- Telegram API changes could break the gateway
- Browser automation could be abused if permissions not properly enforced

## Alternatives Considered

1. **WhatsApp integration instead of Telegram**: Rejected. WhatsApp requires a business account, has message limits, and uses the unofficial Baileys library (which can break). Telegram has an official, stable, free API.

2. **Vector database (ChromaDB/Pinecone) for memory**: Deferred. SQLite FTS5 + a simple facts table is sufficient for single-user. Vector DB adds deployment complexity without proportional benefit at our scale.

3. **Email integration**: Deferred to Phase 9. Privacy complexity is high (OAuth2 flows, email content parsing). Better to prove the memory and multi-channel pattern first.

4. **Native mobile app**: Rejected. PWA provides 90% of the value at 10% of the cost. If PWA proves insufficient, native app can be Phase 9.

5. **Smart scheduling / task management**: Deferred. Calendar integration already exists. Full task management is a separate product concern that should wait until the memory layer proves its value.

## References
- Market research: planner_iteration/research/2026-02-11-phase8-always-on-partner.md
- Retention research: planner_iteration/research/2026-02-11-retention-and-stickiness.md
- Mem0 architecture: https://mem0.ai/blog/ai-memory-layer-guide
- OpenClaw architecture: multi-channel gateway pattern
- PWA best practices: https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Best_practices
