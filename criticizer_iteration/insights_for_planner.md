# Criticizer Insights for Planner

## Repeated Bug Patterns

### Database Concurrency Issues
**Module**: assistant/server/services (memory.py, settings.py)
**Occurrences**: 2 related issues in recent history
- Issue #26: Original database locking bug (still open)
- Issue #31: Event loop attachment bug in ConnectionPool fix (now resolved)

**Pattern**: 
- Initial fix attempts for SQLite concurrency introduce new bugs
- Unit tests pass but don't catch concurrent scenario failures
- Real-world concurrent API testing reveals issues immediately

**Recommendation**: This is a complex area requiring extra scrutiny. Any database-related changes should include concurrent scenario tests.

### Asyncio Event Loop Lifecycle Issues
**Module**: All services using asyncio primitives
**Occurrences**: 1 critical bug (Issue #31)

**Pattern**:
- Creating asyncio.Queue/Lock in `__init__` attaches them to import-time event loop
- When requests run on a different event loop, "attached to a different loop" errors occur
- Easy to miss in unit tests (which run in controlled event loop)

**Root Cause**: Mixing sync initialization with async runtime primitives

**Recommendation**: 
- Always create asyncio primitives in async methods (like `initialize()`)
- Add linting rule or code review checklist for asyncio primitive creation
- Document this pattern in ARCHITECTURE.md

## Test Coverage Blind Spots

### Concurrent Request Scenarios
**Gap**: CI tests don't include concurrent API request scenarios
**Impact**: Critical bugs (90% failure rate) reach "needs verification" stage

**Evidence**:
- Issue #31: Unit tests passed (835/835) but concurrent requests failed 90%
- Issue #26: Unit tests passed but concurrent requests fail 40-60%

**Recommendation**:
1. Add concurrent scenario tests to CI (5-10 parallel requests)
2. Add stress tests to benchmark suite (Issue #7 framework exists)
3. Create "real-world" test preset that simulates actual usage

**Suggested Test Cases**:
```python
# tests/test_concurrent_scenarios.py
async def test_concurrent_chat_requests():
    """Test 10 concurrent chat API requests succeed."""
    tasks = [send_chat_request(f"test {i}") for i in range(10)]
    results = await asyncio.gather(*tasks)
    success_count = sum(1 for r in results if r.status_code == 200)
    assert success_count >= 9, f"Only {success_count}/10 succeeded"

async def test_concurrent_message_writes():
    """Test database can handle concurrent writes."""
    # Test memory service directly with concurrent writes
    ...
```

### Event Loop Lifecycle Testing
**Gap**: No tests verify asyncio primitive creation happens in correct lifecycle phase
**Impact**: Event loop attachment bugs not caught until production-like scenarios

**Recommendation**: Add test that creates service, switches event loops, and verifies it still works

## User Experience Issues

### Error Inconsistency Under Concurrency
**Issue**: Some failed requests return "Internal Server Error" (plain text), others return `{"detail":"database is locked"}` (JSON)

**Impact**: 
- API clients can't reliably parse error responses
- Hard to distinguish error types programmatically

**Recommendation**:
- Ensure all error responses use consistent JSON format
- Add error response schema validation
- Document expected error codes and formats in API docs

### No Retry Mechanism for Transient Failures
**Issue**: Database lock errors are transient (would succeed if retried), but API doesn't retry

**Impact**: Users see failures for requests that would succeed on retry

**Recommendation**:
- Add retry logic at database layer (retry.py exists but may not be used here)
- Return 429 (Too Many Requests) with Retry-After header instead of 500
- Consider request queuing for write operations

## Architectural Concerns

### SQLite Scalability Limit
**Problem**: SQLite with WAL mode + connection pooling still can't handle 10 concurrent writes reliably (40% success rate)

**Evidence**:
- Issue #26 testing: 60% success with 5 concurrent, 40% with 10 concurrent
- Affects multiple services: memory (5-conn pool), settings (3-conn pool), likely alerts, auth, scheduler too

**Impact**: 
- Production deployment with multiple users will fail frequently
- Worse under load (success rate decreases with concurrency)

**Recommendation**:
- **Short-term**: Optimize SQLite usage (increase pool size, optimize transactions, add retry)
- **Long-term**: Consider architectural change:
  - Option A: PostgreSQL for production (better concurrent write handling)
  - Option B: Message queue for writes (serialize to avoid contention)
  - Option C: Split databases by service (reduce contention)
  - Option D: Accept lower concurrency as product constraint (document limits)

**Decision needed**: Planner should decide if this is a blocker for product goals

### Connection Pool Sizing Strategy
**Problem**: No clear rationale for pool sizes (memory: 5, settings: 3)

**Questions**:
- Why different sizes for different services?
- Are these sizes based on expected load or arbitrary?
- Should pool size be configurable?

**Recommendation**: Document pooling strategy in ARCHITECTURE.md with:
- Expected concurrent request load
- Pool size calculation rationale
- When to scale up vs. switch databases

## Positive Patterns Observed

### Multi-Agent Quality Gate Working
**Evidence**: 
- Issue #31: Builder implemented fix → Criticizer caught event loop bug → Fixed properly → Verified
- Issue #26: Builder attempted fix → Criticizer found it insufficient → Remains open (prevented false completion)

**Impact**: System prevented shipping of buggy code

**Recommendation**: Continue this pattern. Builder focus on implementation, Criticizer on verification.

### Builder Following Protocol (Improving)
**Evidence**: Issue #31 had proper `needs-verification` label and comment

**Improvement**: Previous issues (like #26 initially) didn't follow protocol

**Recommendation**: Acknowledge improvement, encourage continuation

## Suggested Priority Changes

None at this time. Current priorities seem appropriate:
- Issue #26 is marked `priority-high` (correct for 40-60% failure rate)
- Issue #31 was `priority-critical` and is now resolved

## Recommendations for Planner

1. **Create architectural decision**: SQLite vs. PostgreSQL for production (Issue #26 reveals scalability limits)

2. **Create new issue**: "Add concurrent scenario tests to CI" (prevent regressions like #31 and #26)

3. **Create new issue**: "Standardize error response format" (improve API reliability)

4. **Update roadmap**: Mark "Production deployment" as blocked by database concurrency resolution

5. **Document pattern**: Add "asyncio primitive lifecycle" section to ARCHITECTURE.md

6. **Consider**: Is 10 concurrent users a product goal? If yes, Issue #26 is critical. If no, document the limit.

---
*Last updated: 2026-02-04 13:58*
*Based on verifications of Issues #21-26, #31*
