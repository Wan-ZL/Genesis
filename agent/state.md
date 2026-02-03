# agent/state.md

## Current Focus
GitHub Issue #1: Implement AI Assistant v1

## Done
- Repo structure and memory rules defined (.claude/CLAUDE.md + rules)
- Hooks system configured (5 hooks)
- Auto-loop mechanism implemented (start-loop.sh + 8-Stop-trigger-next.sh)
- AI Assistant architecture designed (assistant/ARCHITECTURE.md)
- OpenAI API key configured (.claude/openai-key-secrets.env)
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

## Acceptance Criteria Status
- [x] Simple Web UI (input box + message history + status panel)
- [~] Can call Claude API for conversation ← **CODE READY** (needs API key in `.claude/anthropic-key-secrets.env`)
- [x] Support image/PDF upload and processing
- [x] Persist conversation history
- [x] Display current focus and recent runlog status

## Next Step (single step)
Issue #1 complete (pending ANTHROPIC_API_KEY). Eval framework complete with CLI runner. Consider tackling error recovery/auto-restart or CI integration from backlog.

## Risks / Notes
- Without API key, system falls back to OpenAI (still functional)
- Claude vision format differs from OpenAI (implemented)
- PDF support via Claude document type (implemented)
- All other acceptance criteria are met - only API key is blocking completion

## How to test quickly
```bash
cd /Users/zelin/Startups/Genesis/assistant

# Option 1: Run directly
pip3 install -r requirements.txt
python3 -m server.main
# Visit http://127.0.0.1:8080

# Option 2: Install as 24/7 service (macOS)
./service/assistant-service.sh install
./service/assistant-service.sh start
./service/assistant-service.sh status
./service/assistant-service.sh logs
```
