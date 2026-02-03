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

## Acceptance Criteria Status
- [x] Simple Web UI (input box + message history + status panel)
- [~] Can call Claude API for conversation ← **CODE READY** (needs API key in `.claude/anthropic-key-secrets.env`)
- [x] Support image/PDF upload and processing
- [x] Persist conversation history
- [x] Display current focus and recent runlog status

## Next Step (single step)
Integrate tool registry with chat API so assistant can use tools (function calling). Issue #1 remains **BLOCKED** on ANTHROPIC_API_KEY.

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
