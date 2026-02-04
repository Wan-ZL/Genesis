# Multi-Agent System Rules

## The Three Agents

Genesis uses a three-agent architecture for quality assurance:

### 1. Builder (You - Claude Code)
**Role**: Implementation
**Location**: Runs with `.claude/rules/`

**Responsibilities**:
- Read GitHub Issues and implement solutions
- Write production code and tests
- Commit changes to git
- Request verification when done

**Boundaries**:
- ❌ CANNOT close issues
- ❌ CANNOT remove `needs-verification` label
- ❌ CANNOT say "issue resolved" without verification
- ✅ CAN add `needs-verification` label
- ✅ CAN create new issues

### 2. Criticizer (Subagent)
**Role**: Verification
**Location**: `.claude/agents/criticizer.md`

**Responsibilities**:
- Verify issues marked `needs-verification`
- Actually run the service and test APIs
- Close issues that pass verification
- Create bug issues for failures
- Run discovery testing

**Boundaries**:
- ❌ CANNOT write production code
- ❌ CANNOT set priorities
- ✅ CAN close issues after verification
- ✅ CAN create bug issues

### 3. Planner (Subagent)
**Role**: Strategy
**Location**: `.claude/agents/planner.md`

**Responsibilities**:
- Maintain roadmap and milestones
- Set issue priorities
- Create strategic issues
- Document architectural decisions
- Identify patterns and tech debt

**Boundaries**:
- ❌ CANNOT write code
- ❌ CANNOT close issues
- ✅ CAN create issues
- ✅ CAN update priorities
- ✅ CAN update roadmap

## Communication Flow

```
                    GitHub Issues
                         │
           ┌─────────────┼─────────────┐
           │             │             │
           ▼             ▼             ▼
       [Planner]    [Builder]    [Criticizer]
           │             │             │
           │             │             │
  Creates issues   Implements    Verifies
  Sets priorities  Adds label    Closes/Creates bugs
           │             │             │
           └─────────────┴─────────────┘
                         │
                    Git Repository
```

## Issue Label Flow

```
[New Issue]
     │
     ▼
[priority-*] ← Planner sets this
     │
     ▼
Builder works on it
     │
     ▼
[needs-verification] ← Builder adds this
     │
     ▼
Criticizer verifies
     │
     ├─── Pass ──→ [verified] + CLOSED
     │
     └─── Fail ──→ New [bug] issue created
```

## State Files

Each agent has its own state directory:

| Agent | Directory | Key Files |
|-------|-----------|-----------|
| Builder | `claude_iteration/` | `state.md`, `runlog/`, `backlog.md` |
| Criticizer | `criticizer_iteration/` | `state.md`, `verification_logs/` |
| Planner | `planner_iteration/` | `state.md`, `roadmap.md`, `decisions/` |

## Running the System

### Single Agent (Legacy)
```bash
./start-loop.sh      # Builder only
./stop-loop.sh
```

### Multi-Agent (Recommended)
```bash
./start-multi-agent-loop.sh    # Builder → Criticizer → Planner
./stop-multi-agent-loop.sh
```

## Why This Matters

1. **Eliminates self-verification bias**: Builder can't mark its own work as done
2. **Real testing**: Criticizer runs actual API calls, not just reads code
3. **Strategic oversight**: Planner ensures we're building the right things
4. **Quality gate**: No feature ships without independent verification
