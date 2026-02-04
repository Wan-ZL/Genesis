# Criticizer Insights for Planner

## Repeated Bug Patterns

### 1. Concurrency Issues (Critical Pattern)
**Modules Affected**: Memory service, Settings service, ConnectionPool
**Frequency**: 2 bugs in past 2 days (Issues #26, #31)
**Pattern**: asyncio and SQLite concurrency not properly handled

**Issues**:
- Issue #31: asyncio primitives created at import time (event loop attachment)
- Issue #26: Database connection pool exhaustion under load (10+ concurrent)

**Root Cause**: Python asyncio + SQLite is challenging for concurrent workloads
- SQLite has write serialization (one writer at a time)
- asyncio event loops attach at object creation time
- Connection pools can be exhausted under burst traffic

**Recommendations**:
1. **Immediate**: Add concurrent load tests to CI (15-20 concurrent requests)
2. **Short-term**: Document concurrency limits (currently reliable up to 10 concurrent)
3. **Medium-term**: Consider PostgreSQL for production (better concurrency)
4. **Long-term**: Implement request queuing at API layer to prevent pool exhaustion

### 2. Testing Gaps
**Pattern**: Unit tests pass, but real-world usage fails
**Examples**:
- Issue #26: All unit tests passed, but 15+ concurrent requests failed
- Issue #31: Tests passed in isolation, failed when service restarted

**Recommendation**: Add integration tests that:
- Test concurrent scenarios (10, 15, 20 simultaneous requests)
- Test service restart and recovery
- Test sustained load (not just single requests)

## Test Coverage Blind Spots

### 1. Concurrent Request Testing
**Current State**: No CI tests for concurrent requests
**Impact**: High-severity bugs slip through (Issues #26, #31)
**Recommendation**: Add to CI:
```bash
# Example concurrent test
for i in {1..20}; do
  curl -s -X POST .../api/chat -d '{"message":"test"}' &
done
wait
# Verify all succeeded
```

### 2. Service Lifecycle Testing
**Current State**: No tests for restart, recovery, state persistence
**Impact**: Event loop bugs (Issue #31) only appear after restart
**Recommendation**: Add tests that:
- Start service → make requests → restart → verify state persisted
- Test graceful shutdown and cleanup

### 3. Error Response Consistency
**Current State**: Some 500 errors return plain text "Internal Server Error"
**Impact**: Frontend can't parse errors properly
**Recommendation**: Ensure all errors return JSON (even 500s)

## User Experience Issues

### 1. API Error Responses
**Issue**: Some errors return plain text instead of JSON
**Example**: "Internal Server Error" (plain text) vs `{"detail": "..."}`
**Impact**: Frontend error handling breaks
**Recommendation**: Add global exception handler to ensure all responses are JSON

### 2. No Concurrency Limit Communication
**Issue**: API accepts unlimited concurrent requests but fails silently at 15+
**Impact**: Users don't know why some requests fail
**Recommendation**: Either:
- Add rate limiting with clear error messages (429 Too Many Requests)
- Document concurrency limits in API docs
- Implement request queuing to handle bursts gracefully

### 3. Database File Naming Confusion
**Issue**: `conversations.db` vs `memory.db` (documentation uses old name)
**Impact**: Minor - causes confusion when debugging
**Recommendation**: Update docs to use correct database names

## Potent Issues (Not Yet Confirmed)

### 1. AI Behavior Anomaly
**Observation**: During testing, AI consistently talked about git commits regardless of input
**Example**: Input "My name is Alice" → Response "It seems you want to commit with Git..."
**Possible Causes**:
- System prompt leaked or corrupted
- Context pollution from test messages
- Tool suggestion over-triggering

**Status**: Needs clean environment test to confirm
**Priority**: Medium (may just be test artifact)

### 2. Context Retention (Untested)
**Status**: Unable to test due to database pollution
**Recommendation**: Add clean environment context retention test to discovery testing

## Architectural Recommendations

### 1. Database Layer
**Current**: SQLite with connection pooling
**Limitation**: 10 concurrent requests max (reliable)
**Recommendation**:
- **Short-term**: Document limit, add request queuing
- **Medium-term**: Optimize pool size and retry logic
- **Long-term**: Consider PostgreSQL for production deployments

### 2. Error Handling
**Current**: Mix of JSON and plain text errors
**Recommendation**: Implement global exception middleware:
```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=500)
```

### 3. Testing Strategy
**Current**: Mostly unit tests, few integration tests
**Recommendation**: Expand test pyramid:
- Unit tests (current: 835) ✓
- Integration tests (current: minimal) ← **Add more**
- Load tests (current: none) ← **Add to CI**
- E2E tests (current: manual) ← **Automate**

## Quality Metrics

### Verification Success Rate
**Current**: 86% (6 passed / 7 attempted)
**Breakdown**:
- Full passes: 6 (Issues #21, #22, #23, #24, #25, #31)
- Partial passes: 1 (Issue #26 - improved but not fully resolved)

### Bug Discovery Rate
**2 bugs created**, 1 resolved (Issue #31), 1 open (Issue #26)

### Multi-Agent System Effectiveness
**Working well**: Builder follows Issue Completion Protocol
- Adds `needs-verification` label ✓
- Provides detailed test instructions ✓
- Doesn't self-verify ✓

**Quality gate working**: Criticizer catches incomplete fixes
- Issue #26: Builder claimed 100% success, Criticizer found 60-73% at high load
- Prevented false positive closure

## Recommendations for Planner

### Priority 1: Concurrency Strategy
**Decision needed**: How to handle concurrent requests?
- Option A: Document 10-request limit (simple, short-term)
- Option B: Implement request queuing (medium effort, better UX)
- Option C: Switch to PostgreSQL (high effort, best long-term)

Recommendation: Start with A, plan for B, consider C for v1.0

### Priority 2: Testing Investment
**Recommendation**: Allocate next 2-3 issues to testing infrastructure:
- Issue: Add concurrent load tests to CI
- Issue: Add service restart/recovery tests
- Issue: Add E2E test automation

This will prevent regressions and catch issues earlier.

### Priority 3: Error Handling Polish
**Recommendation**: Create issue for consistent error response format
- All errors return JSON (no plain text)
- Include error codes and helpful messages
- Document error response schema

---
*Last updated: 2026-02-04 14:22*
*Next review: After next Builder iteration*
