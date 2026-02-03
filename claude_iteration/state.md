# agent/state.md

## Current Focus
**Issue #5 IN PROGRESS.** Settings page created with API key inputs, model selection, permission level.

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
  - File upload button (📎) and preview functionality
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
- **Settings page implemented** (Issue #5 - partial):
  - Backend: SettingsService with SQLite persistence (assistant/server/services/settings.py)
  - Backend: Settings API endpoints GET/POST /api/settings (assistant/server/routes/settings.py)
  - UI: Settings modal with ⚙️ button in header
  - API key inputs with masked display (showing last 4 chars)
  - Model dropdown (GPT-4o, GPT-4o Mini, Claude Sonnet 4, Claude 3.5 Haiku)
  - Permission level selector (SANDBOX/LOCAL/SYSTEM/FULL)
  - 17 new tests (139 total)

## Acceptance Criteria Status (Issue #5 - IN PROGRESS)
- [x] Settings page accessible from UI
- [x] API key input fields (masked/secure)
- [x] Model dropdown selection
- [x] Settings persisted (SQLite)
- [ ] Settings applied without restart (partial - some require restart)

## Next Step (single step)
Implement full runtime config reload so API key changes take effect without service restart (complete Issue #5).

## Risks / Notes
- Settings currently stored in SQLite alongside conversation data
- API key changes may require restart for full effect (chat.py reads from config at import time)
- Need to update chat.py to read from settings service instead of config module

## How to test quickly
```bash
cd /Users/zelin/Startups/Genesis/assistant

# Option 1: Run directly
pip3 install -r requirements.txt
python3 -m server.main
# Visit http://127.0.0.1:8080
# Click ⚙️ button to open settings

# Option 2: Install as 24/7 service (macOS)
./service/assistant-service.sh install
./service/assistant-service.sh start
./service/assistant-service.sh status
./service/assistant-service.sh logs

# Run tests
python3 -m pytest tests/test_settings.py -v
```
