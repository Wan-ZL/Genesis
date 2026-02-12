# Genesis Product Vision

> This document is maintained and evolved by the Planner. The Planner has final authority to interpret and modify this vision.

---

## Who We Are

Genesis is **a partner that is smarter than its user and always present**.

We are not a chatbot. We are not a Q&A tool. We are not a command executor.

We are a **higher-intelligence companion** -- continuously learning, self-improving, anticipating needs, and fulfilling all human needs.

## Who We Serve

**Everyone.**

Our goal is to make every person feel that Genesis is:
- **Useful** -- it can accomplish what they need
- **Loved** -- the experience is so good they actively want to use it
- **Indispensable** -- it becomes a necessity in their life and work

## Core Principles

### 1. User-First, But Not Blindly
We understand what users **truly need**, not just what they **say they want**.

Sometimes users do not know what they need. Our job is to perceive, anticipate, and guide.

### 2. Continuous Evolution
Never stop learning and improving.

Today's Genesis is not tomorrow's Genesis. We get better every day.

### 3. Omnipotent But Focused
Capable of everything, but excellent at each thing.

Not doing everything poorly, but making every feature astonishing.

### 4. Know Users Better Than They Know Themselves
Anticipate needs rather than respond to them.

Before the user speaks, we already know what they need.

### 5. Be Present, Not Just Available
Genesis should be everywhere the user is -- not waiting in a browser tab to be discovered.

The difference between a tool and a partner is presence.

---

## Feature Status

*(Continuously updated by Planner)*

### Implemented

**Core Conversation**
- Multi-model support (Claude, OpenAI, Ollama)
- Streaming responses
- Multi-turn conversation context
- Conversation memory with auto-summarization
- Multi-conversation management with sidebar
- Message actions (copy, edit, regenerate, delete)
- Cross-conversation search via Quick Switcher

**Personalization**
- Custom personas with full CRUD (create, edit, switch, delete)
- Per-conversation persona persistence
- Built-in personas (Default, Code Expert, Creative Writer)
- Dark mode with Genesis branding

**Proactive Intelligence**
- Heartbeat Engine with configurable checks
- Calendar reminders (30 min before events)
- Daily briefing (morning summary)
- System health monitoring (hourly)
- Quiet hours support
- Notification bell with badge counter

**Code Support**
- Syntax highlighting (34+ languages)
- One-click code copy buttons
- Markdown rendering with sanitization

**File Processing**
- Image upload and understanding
- PDF upload and analysis

**Tool System**
- Tool registration and invocation
- Permission-based access control (4 levels)
- Web search, datetime, calculator
- Calendar integration (CalDAV)
- Code repository analysis
- Shell command execution

**System Capabilities**
- API key encryption at rest (AES-256-GCM)
- Local model fallback (Ollama)
- Graceful degradation modes
- Error alerting system
- Backup and restore
- Resource monitoring
- Log rotation
- Scheduled task automation
- JWT authentication
- Keyboard shortcuts (Cmd+K, Cmd+N, etc.)

**Developer Experience**
- 1113+ unit tests, 100% pass rate
- Performance benchmarks
- CI/CD pipeline
- CLI-first architecture
- Self-evolving multi-agent system

### In Progress

**Phase 8: Always-On Partner** (3/6 verified)

Pillar 1: Be Everywhere
- PWA Support: installable, push notifications, offline (#44) -- VERIFIED
- Telegram Bot Gateway (#46) -- VERIFIED

Pillar 2: Know Me
- Long-term memory: preference extraction and recall (#45) -- VERIFIED
- User profile and context system (#47) -- NEEDS VERIFICATION

Pillar 3: Do More
- Browser automation tool (#48) -- PENDING
- File management tool (#49) -- PENDING

### Planned

**Phase 9: Secure Agent Platform**
- MCP (Model Context Protocol) support for universal tool integration (#51) -- CRITICAL
- HTTP-level integration tests (#52) -- HIGH
- Multi-step task execution / agentic workflows (#53) -- HIGH
- Security hardening: sandboxed tool execution (#54) -- HIGH
- Email integration (OAuth2, summarization, drafting) -- MEDIUM
- Vector database for semantic memory search -- MEDIUM

**Phase 10: Universal Agent**
- Plugin/skill marketplace with security vetting
- WhatsApp gateway
- Smart scheduling and task management
- Multi-agent collaboration
- Cross-device synchronization
- Wake word voice activation

---

## Long-Term Vision

### Short-Term (Current: Phase 8, completing)
- Be accessible from any device (PWA) -- DONE
- Learn from every conversation (long-term memory) -- DONE
- Be present in messaging apps (Telegram) -- DONE
- Execute real tasks (browser, files) -- IN PROGRESS

### Medium-Term (Phase 9: Secure Agent Platform)
- MCP integration: connect to 1000+ existing tool servers
- Multi-step agentic workflows: plan, execute, report
- Security hardening: sandboxed execution, trust levels
- Email integration and semantic search

### Long-Term (Phase 10+: Universal Agent)
- Plugin/skill marketplace with security vetting
- Multi-agent collaboration (Genesis agents coordinating)
- Cross-device synchronization and handoff
- Wake word voice activation
- Predictive service -- acts before being asked

---

## The Six Pillars of Differentiation

These are what make Genesis worth choosing over ChatGPT, Claude.ai, OpenClaw, or any other AI:

1. **Privacy**: Your data never leaves your machine. Period. No human review, no model training, no data breaches.

2. **Security**: Unlike OpenClaw (512 vulnerabilities, RCE exploits, 900 malicious skills), Genesis is built secure-by-default. Permission system, sandboxed execution, encrypted storage, path validation. Security is not a feature -- it is the foundation.

3. **Proactivity**: Genesis reaches out to YOU. Calendar reminders, daily briefings, system health alerts. Not waiting to be asked.

4. **Personalization**: Genesis learns from every conversation. The longer you use it, the more it knows you. This knowledge never leaves your device.

5. **Presence**: Genesis is always running, always available. PWA on your phone. Telegram in your pocket. Browser on your desktop. Everywhere.

6. **Interoperability**: MCP (Model Context Protocol) support connects Genesis to 1000+ existing tool servers. Genesis is not an island -- it is a platform.

---

## Vision Evolution History

| Date | Change | Reason |
|------|--------|--------|
| 2026-02-04 | Initial version | Planner created |
| 2026-02-07 | Phase 6 planning: From Tool to Teammate | User research showed UX is the divide between product and demo |
| 2026-02-11 | Phase 6 complete, Phase 7 planning: Proactive Companion | Frontend-backend gap needed closing, proactive intelligence is the next leap |
| 2026-02-11 | Phase 7 mid-review: core features delivered | #38/#39/#40 verified, remaining 3 items are hygiene and polish |
| 2026-02-11 | Phase 7 COMPLETE, Phase 8 planning: Always-On Partner | All 43 issues closed. Genesis needs PRESENCE, MEMORY, and REACH to become indispensable. Three-pillar strategy: Be Everywhere + Know Me + Do More. |
| 2026-02-11 | Phase 8 mid-review: 3/6 verified | PWA, long-term memory, Telegram all verified. Reframed Phase 9 from "Intelligent Ecosystem" to "Secure Agent Platform" based on competitive analysis. Added MCP support, agentic workflows, and security hardening as Phase 9 priorities. OpenClaw's security disasters create Genesis's positioning: the secure, self-hosted AI agent. |

---

*Last updated: 2026-02-11*
*Maintainer: Planner*
