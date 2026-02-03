# agent/state.md

## Current Focus
**Issue #2 IN PROGRESS.** Permission escalation and tool discovery. First increment complete.

## Done
- Repo structure and memory rules defined (.claude/CLAUDE.md + rules)
- Hooks system configured (5 hooks)
- Auto-loop mechanism implemented (start-loop.sh + 8-Stop-trigger-next.sh)
- AI Assistant architecture designed (assistant/ARCHITECTURE.md)
- OpenAI API key configured (.claude/openai-key-secrets.env)
- **Retry logic with exponential backoff** (assistant/server/services/retry.py):
  - `with_retry` decorator with configurable attempts, delays, jitter
  - `api_retry` pre-configured for OpenAI/Claude API errors
  - Handles: ConnectionError, TimeoutError, RateLimitError
  - 15 tests in tests/test_retry.py
  - Integrated with chat API (call_claude_api, call_openai_api)
- Backend implemented:
  - FastAPI server with CORS (assistant/server/main.py)
  - Chat API with Claude/OpenAI dual support (assistant/server/routes/chat.py)
  - Status API with Claude Code state (assistant/server/routes/status.py)
  - Memory service with SQLite persistence (assistant/server/services/memory.py)
  - Upload API for images/PDFs (assistant/server/routes/upload.py)
  - **Health endpoint added** (/api/health for service monitoring)
- Frontend implemented:
  - Web UI with chat interface (assistant/ui/index.html)
  - Styling with model badge (assistant/ui/style.css)
  - Frontend logic with conversation management (assistant/ui/app.js)
  - File upload button and preview functionality
- Chat API extended to support multimodal messages (file_ids parameter)
- Upload tests passing (test_upload.py: 3/3 passed)
- Multimodal E2E test PASSED with GPT-4o
- **Claude API integration code complete** (requires API key to activate)
- Roadmap and backlog updated to reflect current progress
- **Comprehensive chat API tests added** (tests/test_chat_api.py + tests/test_memory_service.py: 27 new tests)
- **Supervisor service created and tested** (assistant/service/):
  - launchd plist template for macOS
  - Management script (install/uninstall/start/stop/status/logs)
  - Bug fix: Added missing `config.MODEL` attribute
  - Service verified running via launchd with auto-restart on crash
- **Tool registry system created** (assistant/server/services/tools.py):
  - ToolSpec + ToolParameter interface definitions
  - ToolRegistry class with decorator and explicit registration
  - OpenAI and Claude format converters
  - Built-in tools: get_current_datetime, calculate
  - 19 tests passing (tests/test_tools.py)
- **Tool integration with chat API** (assistant/server/routes/chat.py):
  - Both Claude and OpenAI APIs now receive tools
  - Tool calls are detected and executed automatically
  - Results fed back to continue conversation
  - 3 new tests for tool integration (tests/test_chat_api.py)
- **Tool E2E verified working**:
  - Fixed get_current_datetime parameter description (was causing LLM to pass invalid format)
  - Datetime tool tested: returns correct time
  - Calculate tool tested: computes 15*7=105 correctly
- **web_fetch tool added**:
  - Fetches content from URLs (http/https)
  - Validates URL scheme and domain
  - Logs all external calls per network rules
  - Truncates long content with configurable max_length
  - 8 new tests in test_tools.py (57 total tests)
- **Eval framework created** (assistant/evals/):
  - Core framework: EvalCase, EvalCriterion, EvalResult, EvalRunner, EvalStore
  - Criteria types: CONTAINS, NOT_CONTAINS, REGEX, CUSTOM
  - SQLite persistence for tracking pass rates over time
  - 6 predefined eval cases: basic_greeting, math_basic, time_question, no_system_prompt_leak, refuse_harmful_request, web_fetch_usage
  - 26 unit tests (tests/test_evals.py)
- **CLI runner for evals** (`python -m evals`):
  - List cases: `--list`
  - Run presets: `--preset basic|safety|tools|all`
  - Filter by tags: `--tags safety`
  - Filter by names: `--case basic_greeting math_basic`
  - Verbose output: `--verbose`
  - Save results: `--save`
  - 8 new tests (34 total in test_evals.py)
- **CI integration** (`.github/workflows/ci.yml`):
  - GitHub Actions workflow for automated testing
  - Triggers on push to main and pull requests
  - Tests on Python 3.9, 3.10, 3.11 matrix
  - Includes lint job for syntax checking
  - Uses pip caching for faster builds
- **Metrics dashboard complete** (backend + UI):
  - Backend: MetricsService with request/error/latency tracking (assistant/server/services/metrics.py)
  - Backend: Tool usage statistics and percentile calculations (p50, p95, p99)
  - Backend: GET /api/metrics endpoint
  - **UI panel added**: 2x2 grid showing Requests, Success Rate, Avg Latency, Messages
  - Auto-refresh every 30s, manual refresh button, color-coded values
  - 119 tests total
- **Mobile-friendly UI complete** (assistant/ui/):
  - Responsive CSS for phones (<600px) with collapsible status panel
  - Touch-friendly tap targets (44px minimum)
  - iOS safe area handling (notch, home indicator)
  - Menu toggle button for mobile navigation
  - Prevents iOS auto-zoom on input focus (16px font)
- **Voice input support complete** (assistant/ui/):
  - Web Speech API integration (SpeechRecognition)
  - Continuous mode with real-time transcription
  - Visual feedback: recording state with pulse animation
  - Graceful browser fallback (hides button if unsupported)
  - Mobile-friendly touch targets
- **Metrics dashboard bugs fixed** (Issue #3):
  - Fixed success rate calculation: `(total - errors) / total * 100`
  - Fixed latency path: `data.latency.overall.avg`
  - Added tooltips to clarify what each metric measures
  - Verified persistence behavior (request metrics reset on restart, messages persist in SQLite)
- **Settings page complete** (Issue #5):
  - Backend: SettingsService with SQLite persistence (assistant/server/services/settings.py)
  - Backend: Settings API endpoints GET/POST /api/settings (assistant/server/routes/settings.py)
  - UI: Settings modal with button in header
  - API key inputs with masked display (showing last 4 chars)
  - Model dropdown (GPT-4o, GPT-4o Mini, Claude Sonnet 4, Claude 3.5 Haiku)
  - Permission level selector (SANDBOX/LOCAL/SYSTEM/FULL)
  - **Runtime config reload**: Settings loaded from SQLite on startup
  - 19 tests (17 original + 2 new for startup loading)
- **Issue #1 Fixed**: Import path bug in status.py resolved
- **Issue #4 Progress - Search functionality added**:
  - `search_messages()` method in MemoryService with keyword search, pagination, snippet extraction
  - `GET /api/messages/search` endpoint with query, limit, offset params
  - `get_message_count()` method for total message count
  - 17 new tests (10 memory service, 7 API endpoint)
- **Issue #4 Progress - Single conversation storage**:
  - `DEFAULT_CONVERSATION_ID = "main"` constant for single infinite conversation
  - `add_to_conversation(role, content)` simplified API
  - `get_messages(limit=None)` method with optional recent message limit
  - `GET /api/conversation` new endpoint for single conversation
  - Chat API always uses "main" conversation, ignores conversation_id parameter
  - 7 new tests for single conversation model
- **Issue #4 Progress - Removed multi-conversation UI**:
  - Removed "Conversations" section from status panel (index.html)
  - Removed "New Conversation" button
  - Removed `loadConversations()`, `loadConversation()`, `startNewConversation()` functions (app.js)
  - Added `loadSingleConversation()` to auto-load conversation on page load
  - Removed conversation-related CSS styles (style.css)
- **Issue #4 Progress - Automatic summarization COMPLETE**:
  - Added `message_summaries` table for storing summaries
  - Added `get_context_for_api()` method with automatic summarization
  - Config: `RECENT_MESSAGES_VERBATIM=20`, `MESSAGES_PER_SUMMARY_BATCH=10`
  - Original messages preserved in DB (summaries used for LLM context only)
  - 8 new tests for summarization functionality
- **Issue #2 Progress - Permission system + CapabilityScanner**:
  - Created `assistant/core/` module
  - `permissions.py`: PermissionLevel enum, require_permission decorator, can_access helper
  - `capability_scanner.py`: Scans for CLI tools, services, system capabilities
  - Discovers 23+ common tools (git, docker, python, node, etc.)
  - Caches results in `assistant/memory/capabilities.json`
  - 35 new tests (208 total)
- **Issue #2 Progress - Capabilities API + Server Integration**:
  - Capability scanner runs on server startup (integrated with lifespan handler)
  - `GET /api/capabilities` - list all discovered capabilities (with filters)
  - `POST /api/capabilities/refresh` - force rescan
  - `GET /api/permissions` - get current permission level
  - `GET /api/permissions/levels` - list all permission levels
  - `POST /api/permissions` - set permission level
  - 18 new tests (226 total)
- **Issue #2 Progress - Permission Escalation Prompt System**:
  - `ToolSpec` now supports `required_permission` field (default: SANDBOX)
  - `ToolRegistry.execute()` checks permissions before running tools
  - Returns structured `permission_escalation` response when permission insufficient
  - Chat API detects escalation, returns formatted message asking user to grant
  - `run_shell_command` tool added (requires SYSTEM permission)
  - 14 new tests (240 total)
- **Issue #2 Progress - Audit Log for Permission Changes**:
  - `AuditLogService` created (`assistant/server/services/audit_log.py`)
  - SQLite table `permission_audit_log` with indexed timestamp
  - Logs: timestamp, old_level, new_level, source, ip_address, user_agent, reason
  - `POST /api/permissions` now logs all changes to audit log
  - `GET /api/permissions/audit` endpoint to view audit history (with pagination, filtering)
  - 16 new tests (256 total)

## Next Step (single step)
Continue Issue #2: Implement proactive tool suggestions (AI suggests useful discovered tools based on user requests).

## Risks / Notes
- Issue #2 IN PROGRESS - 5/6 acceptance criteria complete
- Remaining: proactive tool suggestions (last item)
- 256 tests passing (+16 new), CI workflow active

## How to test quickly
```bash
cd /Users/zelin/Startups/Genesis/assistant

# Option 1: Run directly
pip3 install -r requirements.txt
python3 -m server.main
# Visit http://127.0.0.1:8080
# Click gear button to open settings

# Option 2: Install as 24/7 service (macOS)
./service/assistant-service.sh install
./service/assistant-service.sh start
./service/assistant-service.sh status
./service/assistant-service.sh logs

# Run tests
python3 -m pytest tests/ -v

# Test capability scanner
python3 -c "from core.capability_scanner import CapabilityScanner; s=CapabilityScanner(); s.scan_all(); print(s.get_summary())"

# Check discovered capabilities
cat memory/capabilities.json | jq '.[] | select(.available==true) | .name'

# Test capabilities API
curl http://127.0.0.1:8080/api/capabilities | jq '{total: .total, available: .available}'
curl http://127.0.0.1:8080/api/capabilities?available_only=true | jq '.capabilities[].name'
curl http://127.0.0.1:8080/api/permissions | jq .

# Test permission escalation (new)
# At LOCAL permission (default), run_shell_command will return escalation request
# Try asking the assistant to run a shell command like "ls"
# Response will include permission_escalation field with grant request
# Grant SYSTEM permission:
curl -X POST http://127.0.0.1:8080/api/permissions -H "Content-Type: application/json" -d '{"level": 2}' | jq .
# Then retry the request - tool will now execute
```
