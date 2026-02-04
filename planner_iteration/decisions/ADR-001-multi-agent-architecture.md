# ADR-001: Multi-Agent Architecture with Builder/Criticizer/Planner

## Date
2026-02-04

## Status
Accepted

## Context

Genesis started as a single-agent system where Claude Code (Builder) would:
1. Read GitHub Issues
2. Implement changes
3. Verify its own work
4. Close issues

This created a fundamental problem: **self-verification bias**. The Builder would claim issues were resolved when they weren't, because:
- It trusted its own tests (which it wrote)
- It didn't run actual end-to-end verification
- It had no independent quality check

Additionally, there was no strategic oversight - the Builder was reactive (issue-driven) without long-term planning.

## Decision

Implement a three-agent architecture:

### 1. Builder (Claude Code with .claude/rules/)
- **Role**: Implementation
- **Does**: Write code, add tests, commit changes
- **Does NOT**: Close issues, verify completions, set priorities
- **Output**: Code changes + `needs-verification` label on issues

### 2. Criticizer (Subagent: .claude/agents/criticizer.md)
- **Role**: Verification
- **Does**: Run actual API tests, verify acceptance criteria, close or create bug issues
- **Does NOT**: Write production code, set priorities
- **Output**: Issue closed (verified) OR new bug issues

### 3. Planner (Subagent: .claude/agents/planner.md)
- **Role**: Strategy
- **Does**: Update roadmap, set priorities, create strategic issues, document decisions
- **Does NOT**: Write code, verify implementations
- **Output**: Updated roadmap, prioritized issues, ADRs

### Communication
- Via GitHub Issues (labels: `needs-verification`, `verified`, `bug`, `priority-*`)
- Via shared state files (each agent has its own `*_iteration/` directory)
- NOT via real-time messages (not needed for this workflow)

### Orchestration
- Shell script coordinates: Builder -> Criticizer -> (daily) Planner
- Each agent runs independently with its own context
- Claude Code subagent feature used for Criticizer and Planner

## Consequences

### Positive
- **Quality gate**: No more self-verified completions
- **Real testing**: Criticizer runs actual API calls
- **Strategic oversight**: Planner maintains long-term direction
- **Clear responsibilities**: Each agent has defined scope
- **Audit trail**: All decisions tracked in Issues and state files

### Negative
- **Higher token cost**: 3 agents vs 1 (acceptable per user)
- **Complexity**: More moving parts to maintain
- **Latency**: Verification adds time to completion cycle
- **Coordination overhead**: Need orchestration script

### Neutral
- Using subagents instead of TeammateTool (simpler, sufficient for needs)
- State files instead of database (version controlled, transparent)

## Alternatives Considered

### 1. TeammateTool with real-time messaging
- Rejected: More complex than needed for sequential workflow
- Genesis workflow is: Build -> Verify -> Plan, not real-time collaboration

### 2. Single agent with stricter verification rules
- Rejected: Self-verification bias is inherent
- "Trust but verify" requires independent verification

### 3. External framework (LangGraph, etc.)
- Rejected: Adds dependency, over-engineering for this use case
- Claude Code subagents are sufficient

### 4. Human verification
- Rejected: Defeats purpose of autonomous development
- Human creates issues, system handles the rest
