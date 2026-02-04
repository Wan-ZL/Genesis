# agent/state.md

## Current Focus
**Issue #26 Complete - Needs Verification.** Concurrent request database lock fix.

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
- **Issue #4 COMPLETE - Automatic summarization**:
  - Added `message_summaries` table for storing summaries
  - Added `get_context_for_api()` method with automatic summarization
  - Config: `RECENT_MESSAGES_VERBATIM=20`, `MESSAGES_PER_SUMMARY_BATCH=10`
  - Original messages preserved in DB (summaries used for LLM context only)
  - 8 new tests for summarization functionality
- **Issue #2 COMPLETE - Permission system + Tool discovery**:
  - Permission system: `assistant/core/permissions.py`
  - Capability scanner: `assistant/core/capability_scanner.py` (23+ tools)
  - Capabilities cached in `assistant/memory/capabilities.json`
  - Capabilities API: `GET/POST /api/capabilities`, `GET/POST /api/permissions`
  - Permission escalation prompts for tools requiring elevated access
  - `run_shell_command` tool requiring SYSTEM permission
  - Audit log: `AuditLogService` with `GET /api/permissions/audit`
  - **Tool suggestions: `ToolSuggestionService` with keyword-to-tool mappings**
  - **System prompt injection with relevant tool suggestions**
  - **Chat response includes `suggested_tools` field**
  - 286 tests total (+30 new for tool suggestions)
- **Issue #6 VERIFIED - Streaming response support**:
  - SSE endpoint `POST /api/chat/stream` with event-based responses
  - Claude streaming: `stream=True` with message_delta events
  - OpenAI streaming: `stream=True` with chunk deltas
  - Tool call handling: stream pauses for tool, emits events, resumes
  - Frontend: Real-time token display, animated progress indicator
  - UI: Tool call progress indicators (success/error/permission states)
  - Graceful error handling and fallback to regular endpoint
  - Memory persistence after streaming completes
  - 22 new tests (308 total)
- **Issue #7 VERIFIED - Performance benchmarks**:
  - Benchmark framework: `assistant/benchmarks/framework.py`
  - CLI runner: `python -m benchmarks`
  - 48 benchmarks covering all critical paths
  - Regression detection with 20% threshold
  - CI workflow: `.github/workflows/benchmarks.yml`
- **Issue #8 VERIFIED - Conversation export/import**:
  - Memory Service: `export_conversation()`, `import_conversation(data, mode)`
  - API: `GET /api/conversation/export`, `POST /api/conversation/import`
  - CLI: `python -m cli export --output file.json`
  - CLI: `python -m cli import --input file.json --mode merge|replace`
  - Export format v1.0 with messages, timestamps, file references
  - Merge mode (skip duplicates) and replace mode (clear existing)
  - 20 new tests (328 total)
- **Issue #9 VERIFIED - Path inconsistency fixed**:
  - Shell scripts: All now use auto-detection `$(cd "$(dirname "$0")" && pwd)`
  - supervisord.conf: Uses `%(ENV_GENESIS_DIR)s` instead of hardcoded path
  - Agent docs (criticizer.md, planner.md): Use `$GENESIS_DIR` placeholder
  - Created `scripts/genesis-env.sh` with validation utility
  - Created `docs/PATHS.md` documenting canonical path usage
  - ARCHITECTURE.md: Updated startup instructions with $GENESIS_DIR
- **Issue #10 VERIFIED - Error alerting system**:
  - AlertService: `assistant/server/services/alerts.py`
    - Error threshold detection (configurable errors/minute)
    - SQLite persistence for alert history
    - Rate limiting to prevent alert spam
    - macOS notification center integration
    - Webhook support for external alerting
  - Alerts API: `assistant/server/routes/alerts.py`
    - `GET /api/health/detailed` - Enhanced health check with component status
    - `GET /api/alerts` - List alerts with filtering
    - `GET /api/alerts/stats` - Statistics
    - `POST /api/alerts/{id}/acknowledge` - Acknowledge alert
  - CLI: `python -m assistant.cli alerts list|stats|acknowledge|clear`
  - 30 new tests (358 total)
- **Issue #11 VERIFIED - Backup and restore**:
  - BackupService: `assistant/server/services/backup.py`
    - `create_backup()` - Creates tar.gz backup of all assistant data
    - `restore()` - Restores from backup with force option
    - `preview_restore()` - Shows what would be restored without changes
    - `verify_backup()` - Verifies backup integrity
    - `list_backups()` - Lists available backups with metadata
    - `schedule_daily_backup()` - Returns cron configuration
    - Backup rotation (keep N most recent, default 10)
  - CLI: `python -m cli backup create|restore|list|verify|schedule`
  - 36 new tests (394 total)
- **Issue #12 VERIFIED - Resource monitoring and limits**:
  - ResourceService: `assistant/server/services/resources.py`
    - `get_memory_usage()` - Process and system memory stats
    - `get_cpu_usage()` - Process and system CPU stats
    - `get_disk_usage()` - Disk space stats with thresholds
    - `get_snapshot()` - Complete resource snapshot
    - `check_rate_limit()` / `record_request()` - Per-client rate limiting
    - `cleanup_old_files()` - Delete files older than max age
    - `cleanup_memory()` - GC and cache clearing
    - Configurable limits: max_memory_mb, max_requests_per_minute, file_max_age_days
    - Status thresholds: WARNING and CRITICAL for memory/CPU/disk
  - API: `GET /api/resources`, `POST /api/resources/cleanup/files|memory`
  - CLI: `python -m cli resources`, `python -m cli resources cleanup|memory`
  - 48 new tests (442 total)
- **Issue #13 Implementation Complete - Log rotation and cleanup**:
  - LoggingService: `assistant/server/services/logging_service.py`
    - `LogConfig` class for configurable log settings
    - RotatingFileHandler for automatic rotation (10MB max, 5 backups)
    - Separate log files: assistant.log, error.log, access.log
    - Environment variable `ASSISTANT_LOG_LEVEL` for log level
    - `cleanup_old_logs()` for old log deletion (30 days default)
    - `tail_log()`, `clear_log()`, `get_stats()`, `list_log_files()` methods
  - main.py updated with access logging middleware
  - CLI: `python -m cli logs tail|list|clear|cleanup`
  - 30 new tests
- **Issue #14 VERIFIED - Graceful degradation modes**:
  - DegradationService with circuit breaker, API fallback, rate limit queue
  - web_fetch tool caching for offline access
  - 68 tests
- **Issue #15 VERIFIED - Authentication layer**:
  - AuthService with JWT tokens, bcrypt password hashing, rate limiting
  - Auth API endpoints (login, logout, refresh, etc.)
  - Authentication middleware in main.py
  - 36 tests
- **Issue #16 VERIFIED - Scheduled task automation**:
  - SchedulerService with cron parsing, SQLite persistence, background runner
  - Schedule API for task CRUD
  - CLI commands for schedule management
  - 51 tests
- **Issue #17 COMPLETE - API key encryption at rest (needs verification)**:
  - EncryptionService: `assistant/server/services/encryption.py`
    - AES-256-GCM authenticated encryption
    - Machine-specific key derivation (platform UUID)
    - PBKDF2 with 480,000 iterations (OWASP 2023)
    - Key file persistence at `memory/.encryption_key_salt`
    - Passphrase-based encryption for portable backups
    - Environment variable key for containerized deployments
    - Key rotation capability
  - SettingsService updated:
    - API keys encrypted on set, decrypted on get
    - `migrate_to_encrypted()` for existing plaintext keys
    - `get_encryption_status()` method
  - CLI: `python -m cli settings encrypt|status`
  - 40 new tests (30 encryption + 10 settings encryption)
- **Issue #19 COMPLETE - Encrypted API keys leak prevention (needs verification)**:
  - Root cause: `_decrypt_if_sensitive()` returned raw encrypted value when encryption unavailable
  - Three-layer protection implemented:
    1. Settings Service: Returns empty on decryption failure (not encrypted value)
    2. Runtime Config: `_validate_api_key()` blocks ENC:v1: prefixed values
    3. API Client: `_validate_api_key_safe()` blocks encrypted keys at client creation
  - Enhanced error logging with exception details
  - Startup validation verifies decryption works
  - 6 new tests for leak prevention
- **Issue #18 COMPLETE - Key rotation TypeError fix (needs verification)**:
  - Root cause: `rotate_key()` only accepted `bytes`, but callers expected to pass `EncryptionService`
  - Fix: Updated signature to `Union[bytes, EncryptionService]`
  - Runtime type detection handles both cases
  - 2 new tests for service instance API
- **Issue #20 COMPLETE - Local model fallback with Ollama (needs verification)**:
  - Ollama API client: `assistant/server/services/ollama.py`
  - Config: `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_ENABLED`, `OLLAMA_TIMEOUT`
  - Degradation modes: `CLOUD_UNAVAILABLE`, `LOCAL_ONLY`
  - Fallback chain: Claude -> OpenAI -> Ollama
  - API endpoints: `/api/ollama/status`, `/api/ollama/models`, `/api/ollama/model`, `/api/ollama/local-only`
  - Health check includes Ollama availability
  - Streaming support for Ollama responses
  - Tool calling support (model-dependent)
  - 31 new tests in `test_ollama.py`
  - Documentation: `assistant/docs/OLLAMA_SETUP.md`
- **Issue #23 VERIFIED - Ollama status inconsistency fix**:
  - Root cause: `DegradationService.__init__()` set Ollama `available=True` by default without verifying
  - Fix: Ollama now defaults to `available=False` until verified
  - Added `initialize_ollama_status()` async method called on server startup
  - Updated `reset_api_health()` to maintain correct semantics (Ollama stays unavailable after reset)
  - `/api/degradation` and `/api/ollama/status` are now consistent
- **Issue #21 COMPLETE - Calendar integration (needs verification)**:
  - CalendarService: `assistant/server/services/calendar.py`
    - CalDAV protocol support (works with iCloud, Google, Fastmail, Nextcloud)
    - Methods: `connect()`, `list_events()`, `create_event()`, `update_event()`, `delete_event()`, `find_free_time()`
    - Conflict detection for overlapping events
    - iCalendar format generation
  - Calendar tools registered in tools.py:
    - `list_events`: List calendar events in date range
    - `create_event`: Create new calendar event
    - `update_event`: Modify existing event
    - `delete_event`: Remove event
    - `find_free_time`: Find available time slots
  - All tools require SYSTEM permission (calendar access is sensitive)
  - Settings: `calendar_caldav_url`, `calendar_username`, `calendar_password`, `calendar_default`, `calendar_enabled`
  - `calendar_password` encrypted at rest (in SENSITIVE_KEYS)
  - 32 new tests in `test_calendar.py`
  - Documentation: `assistant/docs/CALENDAR_SETUP.md`
- **Issue #25 COMPLETE - Repository settings API fix (needs verification)**:
  - Fixed `get_display_settings()` to include `repository_paths` and `repository_max_file_size`
  - Added fields to `SettingsUpdate` model for POST endpoint
  - Added validation (1KB min, 100MB max for file size)
  - 11 new tests (830 total)
- **Issue #24 COMPLETE - Code repository analysis tools (needs verification)**:
  - RepositoryService: `assistant/server/services/repository.py`
    - `read_file()`: Read file contents with line ranges and size limits
    - `list_files()`: List directory with glob patterns and recursion
    - `search_code()`: Regex search with context lines (ripgrep-style)
    - `get_file_info()`: Get file metadata without reading
  - Security features:
    - Path validation (only allowed directories)
    - Path traversal protection (blocks `../`)
    - Sensitive file filtering (.env, credentials, keys, etc.)
    - Binary file detection (extension, MIME, content)
    - Size limits (configurable max)
  - Tools registered in tools.py: `read_file`, `list_files`, `search_code`, `get_file_info`
  - All tools require LOCAL permission
  - Config: `REPOSITORY_PATHS`, `REPOSITORY_MAX_FILE_SIZE`
  - 77 new tests in `test_repository.py`
  - Documentation: `assistant/docs/REPOSITORY_ANALYSIS.md`
  - 821 tests total
- **Issue #22 COMPLETE - Pydantic ConfigDict migration (needs verification)**:
  - Migrated `CreateTaskRequest` from deprecated `class Config` to `model_config = ConfigDict(...)`
  - Added `ConfigDict` import from pydantic
  - No more `PydanticDeprecatedSince20` warnings
  - All 51 scheduler tests pass
- **Issue #26 COMPLETE - Concurrent request database lock fix (needs verification)**:
  - Root cause: SettingsService was using direct `aiosqlite.connect()` without WAL mode or busy timeout
  - Added `ConnectionPool` class to settings.py (matching memory.py pattern)
  - Enabled WAL mode (PRAGMA journal_mode=WAL) for concurrent read/write support
  - Added 30-second busy timeout (PRAGMA busy_timeout=30000)
  - Pool size: 3 connections for settings service
  - All settings tests pass (43/44, one pre-existing test expectation issue)
  - Fix prevents "sqlite3.OperationalError: database is locked" during concurrent chat requests

## Next Step (single step)
Await Criticizer verification of Issue #26. Other open issues: #27, #28, #29 (all medium/high priority).

## Risks / Notes
- Issue #26 implementation complete, awaiting verification
- Issue #22 implementation complete, awaiting verification
- Issues #24 and #25 verified and closed by Criticizer
- 830 tests passing (43/44 settings tests pass, one pre-existing default permission level mismatch)
- No other `class Config` patterns found in codebase
- Encryption key salt must be backed up for data recovery
- Other services (alerts, auth, scheduler, audit_log) still use direct aiosqlite.connect() - may need future fix
- SettingsService was the primary bottleneck affecting /api/chat concurrency

## How to test quickly
```bash
cd $GENESIS_DIR/assistant  # or cd assistant/ from project root

# Run all tests
python3 -m pytest tests/ -v

# Test Pydantic ConfigDict migration (Issue #22)
python3 -W error::DeprecationWarning -c "
from server.routes.schedule import CreateTaskRequest
req = CreateTaskRequest(
    name='Test',
    task_type='one_time',
    schedule='2026-12-01T10:00:00',
    action='log',
    action_params={}
)
print('model_config present:', hasattr(CreateTaskRequest, 'model_config'))
print('Instance created:', req.name)
"

# Run scheduler tests
python3 -m pytest tests/test_scheduler.py -v

# Verify no class Config patterns remain
grep -r "class Config:" server --include="*.py"
# Should return no results
```
