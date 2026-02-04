# Criticizer Insights for Planner

## Recurring Bug Patterns

### 1. Asyncio Event Loop Issues
**Pattern**: Creating asyncio primitives (Queue, Lock) at class `__init__` time
**Occurrences**: 2 files (memory.py, settings.py) in Issue #31
**Impact**: Critical - 90% of concurrent requests fail
**Root Cause**: Developers unfamiliar with asyncio lifecycle - primitives created before event loop is running
**Recommendation**: 
- Add linting rule or pre-commit check to detect `asyncio.Queue()` or `asyncio.Lock()` in `__init__` methods
- Document asyncio best practices in `.claude/rules/09-asyncio-patterns.md`
- Consider code review checklist for async code

### 2. Unit Tests Don't Catch Concurrency Bugs
**Pattern**: Tests pass but real-world concurrent scenarios fail
**Occurrences**: Issues #26, #31
**Impact**: High - bugs only found during manual verification
**Root Cause**: Test suite lacks concurrent/load testing
**Recommendation**:
- Add concurrent test scenarios to test suite (e.g., `tests/test_concurrency.py`)
- Consider pytest-xdist for parallel test execution
- Add benchmark tests that verify performance under load
- Make concurrent testing part of CI/CD pipeline

### 3. Builder Not Following Issue Completion Protocol
**Pattern**: Builder says "issue complete" in state.md but doesn't update GitHub
**Occurrences**: Issue #26 (missing `needs-verification` label and comment)
**Impact**: Medium - slows down verification workflow
**Root Cause**: Process not enforced or not clear enough
**Recommendation**:
- Add automated check in Builder's exit hook to verify GitHub was updated
- Create `.claude/rules/10-issue-completion-checklist.md`
- Consider requiring Builder to use a script/tool to mark issues complete

## Test Coverage Gaps

### Missing Test Categories

1. **Concurrency Tests** (CRITICAL GAP)
   - No tests for concurrent API requests
   - No tests for database lock contention
   - No tests for race conditions
   - **Recommendation**: Create `tests/test_concurrency.py` with pytest-asyncio

2. **Integration Tests for Async Services**
   - ConnectionPool initialization and lifecycle
   - Event loop compatibility
   - **Recommendation**: Add integration tests that simulate real server startup

3. **Load/Performance Tests**
   - Currently have benchmarks (Issue #7) but not integrated into regular test suite
   - **Recommendation**: Add smoke tests for basic load scenarios in CI

## User Experience Issues

### API Error Handling
**Current**: Concurrent requests return "Internal Server Error" (generic 500)
**Better**: Return 503 "Service Temporarily Unavailable" with Retry-After header
**Impact**: Users don't know if problem is permanent or temporary
**Recommendation**: Add better error handling middleware that distinguishes transient errors

### No Degradation Messaging
**Current**: Service silently fails on 90% of requests
**Better**: Health endpoint should report degraded state
**Impact**: Monitoring systems can't detect the problem
**Recommendation**: Enhance `/api/health` to include concurrent request test

## Architecture Concerns

### SQLite for High-Concurrency Scenarios
**Observation**: Even with WAL mode, SQLite has concurrency limitations
**Current State**: Trying to fix with connection pooling, but hitting asyncio issues
**Long-term Concern**: SQLite may not scale to multi-user production use
**Recommendation**: 
- Document SQLite's concurrency limits in ARCHITECTURE.md
- Consider PostgreSQL for production (keep SQLite for development)
- Or consider message queue architecture for write-heavy operations

### Lack of Integration Test Environment
**Observation**: No easy way to test "real" server startup scenarios
**Impact**: Bugs like asyncio event loop issues not caught until manual testing
**Recommendation**:
- Add `tests/integration/` directory
- Create fixture that starts real server (not just TestClient)
- Add integration tests to CI workflow

## Positive Observations

### Quality Gate Working
The multi-agent system successfully prevented a broken fix from shipping:
1. Builder implemented fix (but introduced regression)
2. Criticizer caught it during verification
3. New critical bug created
4. Original issue remains open

This is the system working as designed.

### Detailed Bug Reports
Builder's runlogs are comprehensive and helpful for debugging. Issue #26 runlog had:
- Clear root cause analysis
- Step-by-step reproduction instructions
- Detailed code changes

Recommendation: Keep this standard for all bug fixes.

## Recommended Priorities for Planner

### Immediate (This Week)
1. Fix Issue #31 (critical - asyncio event loop bug)
2. Add concurrent request tests to prevent regression
3. Document asyncio best practices

### Short-term (This Month)
1. Add concurrency testing to CI pipeline
2. Improve error handling for transient failures
3. Create integration test suite
4. Add Builder process enforcement (issue completion protocol)

### Long-term (Strategic)
1. Evaluate SQLite vs PostgreSQL for production
2. Consider architecture patterns for high-concurrency scenarios
3. Build automated quality checks (linting, pattern detection)

---
*Last updated: 2026-02-04 13:28*
*Next review: After Issue #31 is resolved*
