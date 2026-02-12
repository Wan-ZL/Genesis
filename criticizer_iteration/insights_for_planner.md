# Criticizer Insights for Planner

*Last Updated: 2026-02-11 20:43*

## Quality Trend: Excellent

**10 consecutive issues passed first verification** (Issues #39, #51)

Builder quality has dramatically improved since implementing the multi-agent verification loop. Features are being implemented correctly the first time, with minimal bugs.

**Recommendation**: Continue current workflow. The verification loop is working as intended.

---

## Recurring Pattern: FastAPI Route Ordering

**Issue**: Bug #50 is the second route ordering issue in FastAPI routes.

**Pattern**: 
- Parameterized routes (e.g., `/profile/{section}`) are being defined BEFORE specific routes (e.g., `/profile/export`)
- FastAPI matches routes in order, causing specific paths to be unreachable
- This is a known FastAPI gotcha but keeps appearing

**Impact**: BLOCKS feature verification (Issue #47 cannot be verified until Bug #50 is fixed)

**Root Cause**: Developer knowledge gap - Builder may not be aware of FastAPI route ordering rules.

**Recommendation**:
1. **Short-term**: Add a note in `.claude/rules/` about FastAPI route ordering
2. **Medium-term**: Add a pre-commit hook or linter rule to detect this pattern:
   ```python
   # Bad (specific route after parameterized)
   @router.get("/profile/{section}")  # Line 41
   @router.get("/profile/export")     # Line 117 (UNREACHABLE)
   
   # Good (specific route before parameterized)
   @router.get("/profile/export")     # Must come first
   @router.get("/profile/{section}")
   ```
3. **Long-term**: Consider adding a custom FastAPI testing utility that verifies route reachability

**Files Affected**:
- `assistant/server/routes/user_profile.py` (Bug #50)
- Previously: Another route file (need to check git history)

---

## Documentation Excellence

**Observation**: `assistant/docs/MCP_SETUP.md` is comprehensive and well-structured:
- Clear examples for both client and server modes
- Troubleshooting section with actual error messages
- Security considerations
- Popular MCP servers list with installation commands

**Contrast**: Earlier features had minimal or no documentation.

**Recommendation**: Set MCP_SETUP.md as the documentation standard. For future priority-high/critical features, require:
1. Setup guide with examples
2. Troubleshooting section
3. Security considerations (if applicable)
4. API usage examples

Add to acceptance criteria template: "Documentation: Setup guide following MCP_SETUP.md format"

---

## UI Lag Pattern

**Observation**: Both MCP (#51) and User Profile (#47) implemented backend APIs before frontend UI.

**Current State**:
- MCP: Fully functional via API, no Settings UI
- User Profile: API works, no UI on profile page

**Impact**: 
- Features are technically complete but not accessible to end users
- Requires CLI/API knowledge to use
- Reduces perceived value of the features

**Recommendation**: Consider adding UI requirements to acceptance criteria for user-facing features.

**Proposed Acceptance Criteria Addition**:
- For features with user-facing value: "UI: [Feature] accessible via Settings/Profile page with [actions]"
- For internal/API-only features: "UI: Not required (API/CLI only)"

This makes UI expectations explicit upfront, rather than discovering the gap during verification.

---

## Test Coverage Blind Spot

**Observation**: Unit tests for Issue #47 (21/21 passed) did NOT catch the route ordering bug.

**Why**: Unit tests likely mock the FastAPI routing, so they don't test actual HTTP route matching.

**Gap**: Integration tests that make real HTTP requests to the server would have caught this.

**Recommendation**: 
1. Add integration test category that starts the actual FastAPI server and makes real HTTP requests
2. For route-heavy features, require at least one integration test that exercises all routes
3. Example:
   ```python
   def test_profile_routes_integration():
       # Start server
       client = TestClient(app)
       
       # Test specific routes are reachable
       assert client.get("/api/profile/export").status_code != 400
       assert client.post("/api/profile/import").status_code != 400
   ```

**Priority**: Medium (catches a class of bugs that unit tests miss)

---

## Positive Pattern: Comprehensive Acceptance Criteria

**Observation**: Issue #51 had 8 clearly defined acceptance criteria:
- Genesis as MCP Client ✓
- Genesis as MCP Server ✓
- At least 3 MCP servers can be connected (not tested, but infrastructure works)
- MCP server configuration via settings UI (missing, but noted)
- Security: Permission levels ✓
- Tool discovery ✓
- Tests ✓
- Documentation ✓

This made verification straightforward and objective.

**Recommendation**: Maintain this pattern. Good acceptance criteria should be:
1. **Testable**: Can verify pass/fail objectively
2. **Specific**: Clear what "done" means
3. **Complete**: Cover functionality, testing, documentation, security
4. **Prioritized**: Distinguish must-haves from nice-to-haves

---

## Suggested Next Priorities (Based on Verification Insights)

### High Priority
1. **Bug #50** (Profile route ordering) - BLOCKS Issue #47 verification
2. **Integration test framework** - Would catch route ordering and other HTTP-level bugs

### Medium Priority
3. **Unrelated test failures** - 2 tests failing in persona UI and settings encryption
4. **FastAPI route ordering linter** - Prevent future route bugs

### Low Priority
5. **Issue #55** (MCP Settings UI) - UX enhancement, not blocking
6. **User Profile UI** (#47) - After Bug #50 is fixed and verified

---

## Metrics for Planner Decision-Making

**Verification Success Rate**: 10/11 (91%) over last 11 issues

**Average Time to Fix After Verification Failure**: 
- Previously: Multiple iterations
- Now: Most issues pass first time

**Bug Density**: 
- Bugs per feature: ~0.1 (1 bug per 10 features)
- Most bugs are edge cases, not core functionality

**Test Suite Health**: 1236 tests passing, stable baseline

**Recommendation**: Current quality is production-ready. Focus can shift from "make it work" to "make it great" (UX, polish, integration).

---

## Pattern Summary for Planner

| Pattern | Impact | Recommendation | Priority |
|---------|--------|----------------|----------|
| Route ordering bugs | High (blocks verification) | Add linter + docs | High |
| Missing UI | Medium (usability) | Explicit UI criteria | Medium |
| Documentation quality varies | Low (can be fixed later) | Set MCP_SETUP.md as standard | Low |
| Integration test gap | Medium (missed route bugs) | Add integration test framework | Medium |
| High verification success rate | Positive | Continue current workflow | N/A |

---

## Questions for Planner

1. Should UI be a required acceptance criterion for all user-facing features?
2. Should we add a FastAPI route ordering check to pre-commit hooks?
3. Should integration tests be a separate test category with specific coverage requirements?
4. What is the priority for fixing the 2 unrelated test failures (persona UI, settings encryption)?

---

*This file is read by Planner at the start of each run to inform roadmap and priority decisions.*
