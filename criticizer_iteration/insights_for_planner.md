# Criticizer Insights for Planner

## Repeated Bug Patterns

### 1. SQLite Concurrency Issues (High Priority)
**Pattern**: Database locking errors under concurrent load
**Occurrences**: 
- Issue #26 (current): Concurrent chat requests fail at 15-20+ concurrency
- Issue #31 (resolved): Event loop attachment bug in connection pool
- Previous testing: Multiple instances of "database is locked" errors

**Root Cause**: SQLite architectural limitations:
- Single write lock per database
- Even with WAL mode, heavy concurrent writes cause contention
- Connection pooling + retry logic helps but doesn't eliminate the issue

**Impact**: 
- Current state: Reliably handles ≤10 concurrent requests (100% success)
- Fails at: 15-20+ concurrent (50-93% success, inconsistent)

**Recommendations for Planner**:
1. **Short-term**: Document the 10-request concurrency limit, add rate limiting
2. **Medium-term**: Optimize transaction scope, increase pool size to 20-30
3. **Long-term**: Migrate to PostgreSQL for production deployments

### 2. Configuration Management Complexity (Medium Priority)
**Pattern**: Users confused about where configuration is stored
**Occurrences**:
- Issue #27: API keys in both .env files and SQLite, UI showed "Not set"
- Related: Multiple configuration sources (.env, SQLite, config.py)

**Root Cause**: No single source of truth for configuration
- .env files for initial setup
- SQLite for runtime user preferences
- config.py as code-level defaults

**Impact**: 
- User confusion about configuration status
- Potential security issues (keys in multiple places)

**Recommendations for Planner**:
1. Document configuration precedence clearly
2. Consider migrating all user-facing settings to SQLite only
3. Use .env only for developer/deployment environment variables

---

## Test Coverage Blind Spots

### 1. Concurrency Stress Testing
**Gap**: No CI/CD tests for concurrent request handling
**Risk**: Regressions in concurrency handling won't be caught

**Recommendation**: Add concurrency stress tests to CI pipeline
```python
# Example test
def test_concurrent_load_10_requests():
    """Verify service handles 10 concurrent requests reliably"""
    # Run 10 concurrent requests
    # Assert 100% success rate
```

### 2. Error Response Format Consistency
**Gap**: Some errors return "Internal Server Error" plain text instead of JSON
**Observed**: Issue #26 - concurrent failures sometimes return plain text

**Recommendation**: Add test to verify all error responses are valid JSON
```python
def test_all_errors_return_json():
    """Verify error responses are always valid JSON"""
    # Test various error scenarios
    # Assert all responses parse as JSON
```

### 3. Database Migration Testing
**Gap**: No tests for upgrading database schema with existing data
**Risk**: Schema changes could break existing deployments

**Recommendation**: Add migration tests before implementing schema changes

---

## User Experience Issues

### 1. Inconsistent Error Messages
**Observation**: 
- Some errors: `{"detail": "database is locked"}` (good, JSON)
- Other errors: `Internal Server Error` (bad, plain text)

**Impact**: Frontend can't reliably parse errors

**Recommendation**: Standardize error response format across all endpoints

### 2. No User-Facing Concurrency Limits
**Observation**: Service silently fails at high concurrency
**Expected**: HTTP 429 (Too Many Requests) with Retry-After header

**Recommendation**: Implement rate limiting at API layer with proper HTTP status codes

### 3. Settings UI Confusion (Resolved in #27)
**Observation**: Users didn't know if API keys were configured
**Resolution**: UI now shows combined status from .env + SQLite

**Lesson Learned**: Always provide clear status visibility to users

---

## Potential Feature Requests (Based on Testing Observations)

### 1. Health Check Endpoint Enhancement
**Current**: `/api/health` returns basic status
**Suggestion**: Add more metrics:
- Current concurrent request count
- Database connection pool utilization
- Error rate (last 1 min, 5 min, 15 min)
- Queue depth (if rate limiting implemented)

### 2. Request Queuing
**Observation**: Concurrent requests beyond pool capacity fail immediately
**Suggestion**: Queue requests when pool is exhausted, with configurable timeout

### 3. Database Connection Pool Monitoring
**Observation**: No visibility into pool exhaustion
**Suggestion**: Expose pool metrics via `/api/metrics` endpoint

---

## Architectural Concerns

### 1. SQLite for Production Use
**Concern**: SQLite has well-known concurrency limitations
**Current Impact**: Handles ≤10 concurrent requests reliably
**Future Risk**: If user load increases, will hit limits

**Recommendation for Planner**: 
- Document SQLite as suitable for single-user or low-concurrency deployments
- Plan PostgreSQL migration path for multi-user or high-traffic deployments
- Consider offering both: SQLite for simplicity, PostgreSQL for scale

### 2. Error Handling Consistency
**Concern**: Mixed error response formats (JSON vs plain text)
**Impact**: Frontend error handling is fragile

**Recommendation**: Implement consistent error middleware in FastAPI

### 3. Testing Strategy
**Concern**: Manual verification catches issues that automated tests miss
**Impact**: Slow feedback loop, regressions possible

**Recommendation**: 
- Expand test coverage for concurrency scenarios
- Add integration tests that actually start the server
- Consider load testing in CI for critical endpoints

---

## Success Stories (What's Working Well)

### 1. Connection Pool + Retry Logic
- Significantly improved concurrency handling (from 20-40% to 100% at ≤10 concurrent)
- Retry with exponential backoff elegantly handles transient lock errors
- Unit tests for concurrency are comprehensive

### 2. Configuration Fallback Logic (Issue #27)
- Clean implementation: `settings.get("key") or config.KEY or ""`
- Good test coverage with edge cases
- User-friendly (shows status from multiple sources)

### 3. Test Infrastructure
- Comprehensive unit tests for core functionality
- Good use of pytest fixtures
- Tests are fast and reliable

---

## Metrics Summary

### Verification Session: 2026-02-04

| Metric | Count |
|--------|-------|
| Issues verified | 2 |
| Issues closed | 1 (#27) |
| Issues failed verification | 1 (#26) |
| Bugs created | 0 |
| Test scenarios run | 15+ |
| Unit tests run | 50+ |

### Historical Pattern (Last 5 Verifications)

| Pattern | Frequency |
|---------|-----------|
| SQLite concurrency issues | 3/5 issues |
| Configuration management | 2/5 issues |
| Asyncio event loop bugs | 1/5 issues |

---

## Recommendations for Next Sprint

1. **Resolve Issue #26**: Choose one of:
   - Option A: Document 10-request limit + add rate limiting (1-2 hours)
   - Option B: Implement additional scaling fixes (4-8 hours)
   - Option C: Plan PostgreSQL migration (1-2 weeks)

2. **Add Concurrency Tests to CI**: Prevent regressions

3. **Standardize Error Responses**: All endpoints return JSON

4. **Enhance Monitoring**: Add `/api/metrics` endpoint with pool utilization

5. **Documentation**: Add "Deployment Considerations" section covering:
   - Concurrency limits
   - When to use PostgreSQL vs SQLite
   - Rate limiting recommendations

---

*Last updated: 2026-02-04 15:15 by Criticizer agent*
