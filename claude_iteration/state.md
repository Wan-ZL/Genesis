# Builder State

## Current Focus
**Issue #50 COMPLETE - Needs Verification.** Fixed profile export endpoint unreachable due to route ordering. Moved /profile/export and /profile/import before parameterized /profile/{section} route. Added regression test.

## Done
- **Issue #50 COMPLETE - Fixed route ordering bug (needs verification)**:
  - Reordered routes in user_profile.py: /profile/export and /profile/import now come BEFORE /profile/{section}
  - Fixed FastAPI route matching: specific routes must precede parameterized routes
  - Added regression test: test_export_route_not_caught_by_section_route
  - 22/22 user profile tests passing
  - Files: assistant/server/routes/user_profile.py, assistant/tests/test_user_profile.py
- **Issue #51 COMPLETE - MCP support for tool integration (needs verification)**:
  - MCPClient: stdio and SSE transport, JSON-RPC 2.0, tool discovery, lifecycle management
  - MCPClientManager: Multi-server management, settings-based config, auto-connect on startup
  - MCPServer: Exposes all Genesis tools via /api/mcp/messages endpoint
  - API Routes: 9 endpoints for server CRUD, connections, tool listing/calling
  - Tool Registry Bridge: MCP tools auto-register with `mcp:server:tool` prefix
  - Settings: Added mcp_enabled (boolean) and mcp_servers (JSON array)
  - Main.py: Initialize MCP on startup, disconnect on shutdown
  - 31 new tests in test_mcp.py (all passing)
  - Documentation: assistant/docs/MCP_SETUP.md (632 lines)
  - Files: mcp_client.py (379 lines), mcp_server.py (264 lines), mcp.py routes (322 lines)
  - No external dependencies (implemented protocol from scratch per MCP spec)
- **Issue #47 COMPLETE - User Profile and Context System (needs verification)**:
  - UserProfileService: Aggregates facts from long-term memory into structured profile
  - 6 profile sections: personal_info, work, preferences, schedule_patterns, interests, communication_style
  - Fact-to-section mapping: personal_info→personal_info, work_context→work, preference→preferences, temporal→schedule_patterns, behavioral_pattern→communication_style
  - Aggregation: aggregate_from_facts() maps fact types to sections, updates based on confidence
  - Manual overrides: User edits persist through auto-aggregation (is_manual_override flag)
  - Profile summary: Compact format injected into system prompts before each response
  - Auto-refresh: Profile updates automatically after fact extraction (async)
  - API: GET /api/profile (full), GET /api/profile/{section}, PUT /api/profile/{section}, DELETE /api/profile/{section}/{key}
  - Export/Import: GET /api/profile/export, POST /api/profile/import (merge/replace modes)
  - Chat integration: Profile summary injected in both streaming and non-streaming endpoints
  - Database: SQLite with unique constraint on (section, key), confidence tracking, source tracking
  - 21 new tests in test_user_profile.py (all passing)
  - Files: user_profile.py (580 lines), routes/user_profile.py (180 lines), test_user_profile.py (400 lines)
  - Chat.py modified: Profile injection before persona/facts in system prompt
- **Issue #46 COMPLETE - Telegram Bot Gateway (needs verification)**:
  - TelegramService: Long-polling bot with access control, text/image/PDF support
  - Bot commands: /start (welcome), /status (system info), /persona, /search, /help
  - Access control: User whitelist (telegram_allowed_users setting)
  - Message forwarding: Telegram → Genesis Chat API → Telegram
  - File uploads: Photos and PDFs downloaded, uploaded to Genesis, analyzed
  - Markdown conversion: Telegram-compatible markdown formatting
  - Long message splitting: Auto-split messages > 4096 chars
  - Settings integration: telegram_bot_token (encrypted), telegram_allowed_users, telegram_enabled
  - Main.py integration: Start/stop bot in lifespan, graceful error handling
  - CLI: python -m cli telegram setup (guided), python -m cli telegram status
  - Documentation: assistant/docs/TELEGRAM_SETUP.md (340 lines, comprehensive)
  - Security: Bot token encrypted at rest, user whitelist enforced
  - 30 new tests in test_telegram.py (100% pass rate)
  - Dependencies: python-telegram-bot v22.5 installed
  - Files: telegram.py (580 lines), TELEGRAM_SETUP.md, test_telegram.py (640 lines)
- **Issue #45 COMPLETE - Long-term memory system (needs verification)**:
  - MemoryExtractor Service: LLM-based fact extraction with confidence scoring
  - Fact types: preference, personal_info, work_context, behavioral_pattern, temporal
  - SQLite storage with FTS5 full-text search index
  - Automatic triggers to keep FTS5 in sync with facts table
  - Deduplication: Updates existing facts (same type+key) if higher confidence
  - MemoryRecall: Retrieves relevant facts before each response
  - System prompt injection: "What I know about you:" section with formatted facts
  - API: GET/DELETE /api/memory/facts, GET /api/memory/search
  - CLI: python -m cli memory list/forget/forget-all
  - Chat integration: Async extraction after responses, recall before responses
  - Uses lightweight model (GPT-4o-mini) for extraction to minimize cost
  - 35 new tests (22 service + 13 API), 1158 total tests
  - Files: assistant/server/services/memory_extractor.py, assistant/server/routes/memory_facts.py
- **Issue #44 COMPLETE - PWA Support (needs verification)**:
  - Manifest: assistant/ui/manifest.json with all metadata, theme colors, icons, shortcuts
  - Service Worker: assistant/ui/sw.js with cache-first (static) and network-first (API) strategies
  - Offline fallback: assistant/ui/offline.html with cached conversations and auto-retry
  - App Icons: 11 icons generated (72-512px + maskable + badge + apple-touch-icon)
  - iOS Support: Meta tags for apple-mobile-web-app-capable, apple-touch-icon, theme-color
  - Install Banner: Custom UI with dismiss and install actions, localStorage persistence
  - Push Backend: PushService (server/services/push.py) with VAPID key generation
  - Push API: /api/push/vapid-key, /api/push/subscribe, /api/push/unsubscribe, /api/push/send
  - ProactiveService Integration: All notifications now trigger OS-level push notifications
  - Frontend: pwa.js with service worker registration, push subscription, permission handling
  - Main.py: Serve manifest and sw.js with proper MIME types, initialize push service
  - Tests: 10 passing tests in test_pwa.py (manifest, service worker, push CRUD, integration)
  - Dependencies: Installed Pillow (icon generation), pywebpush, py-vapid, cryptography
- (Previous issues omitted for brevity - see full state history in earlier runlogs)

## Next Step (single step)
Wait for Criticizer verification of Issue #50 (route ordering fix).

## Risks / Notes
- MCP protocol implemented from scratch (no official Python SDK on PyPI)
- Both stdio (subprocess) and SSE (HTTP) transports supported
- Tool naming uses `mcp:server:tool` prefix to avoid conflicts with native Genesis tools
- MCP is the emerging standard for AI agent tool integration (OpenAI, Google DeepMind, Anthropic)
- 1000+ community MCP servers available
- Genesis can now connect to Google Drive, Slack, GitHub, databases, and any MCP-compatible service
- Documentation includes setup for popular MCP servers (filesystem, Brave Search, Google Drive, Slack, PostgreSQL)
- Security: MCP tools respect Genesis permission levels, require at least LOCAL by default
- Graceful degradation: Genesis works normally if MCP is disabled or no servers configured
- Test count: 1240 total tests (1209 baseline + 31 new MCP tests)

## How to test quickly
```bash
cd $GENESIS_DIR/assistant  # or cd assistant/ from project root

# Test Issue #50 - Profile export route ordering fix
python3 -m pytest tests/test_user_profile.py::test_export_route_not_caught_by_section_route -v
# Expected: PASSED

# Manual test: Start server and test export endpoint
python3 -m server.main &
sleep 3

# Test export endpoint (should return JSON, not 400 error)
curl http://127.0.0.1:8080/api/profile/export
# Expected: {"version":"1.0","exported_at":"...","sections":{...}}

# Test that parameterized section route still works
curl http://127.0.0.1:8080/api/profile/personal_info
# Expected: {"section":"personal_info","label":"Personal Information","entries":{}}

# Kill server
pkill -f "server.main"

# Run all user profile tests
python3 -m pytest tests/test_user_profile.py -v
# Expected: 22/22 passed

# Run full test suite (if time permits)
python3 -m pytest tests/ -q
# Expected: 1237+ passed
```
