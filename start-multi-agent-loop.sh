#!/bin/bash
# Genesis Multi-Agent Loop with Self-Healing
# Coordinates Builder -> Criticizer -> Planner
# Features: Heartbeat detection, Circuit breaker, Zombie cleanup

set -e

# Auto-detect GENESIS_DIR from script location
GENESIS_DIR="$(cd "$(dirname "$0")" && pwd)"
LOOP_FLAG_FILE="$GENESIS_DIR/hooks/loop_multi_agent.txt"
LOG_DIR="$GENESIS_DIR/orchestration_logs"
ORCHESTRATOR_DIR="$GENESIS_DIR/orchestrator"
CB_FILE="$ORCHESTRATOR_DIR/.circuit_breaker.json"
HEARTBEAT_FILE="/tmp/genesis_heartbeat.json"
ITERATION_COUNT=0

# Configuration
HEARTBEAT_STALE_MINUTES=15      # Minutes before considering agent stuck
HEARTBEAT_CHECK_INTERVAL=60     # Seconds between heartbeat checks
AGENT_MAX_RUNTIME_MINUTES=45    # Max total runtime per agent (even with good heartbeat)
CB_WARNING_THRESHOLD=3          # Iterations without progress before warning
CB_STOP_THRESHOLD=5             # Iterations without progress before stopping

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Create directories
mkdir -p "$LOG_DIR"
mkdir -p "$ORCHESTRATOR_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Genesis Multi-Agent Loop Starting   ${NC}"
echo -e "${BLUE}   (with Self-Healing Mechanisms)      ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Project: $GENESIS_DIR"
echo "Logs: $LOG_DIR"
echo "Heartbeat timeout: ${HEARTBEAT_STALE_MINUTES} minutes"
echo "Circuit breaker threshold: ${CB_STOP_THRESHOLD} iterations"
echo "Stop: Create $LOOP_FLAG_FILE with content 'false' or Ctrl+C"
echo ""

# Initialize loop flag
echo "true" > "$LOOP_FLAG_FILE"

#=============================================================================
# CIRCUIT BREAKER FUNCTIONS
#=============================================================================

init_circuit_breaker() {
    # Always reset on loop start - stale state from previous runs should not block new runs
    echo '{"state":"CLOSED","no_progress_count":0,"last_progress_iteration":0}' > "$CB_FILE"
}

# Check if there are uncommitted git changes (progress indicator)
# Must be called BEFORE git_sync, otherwise git_sync commits everything and this always returns false
has_uncommitted_changes() {
    cd "$GENESIS_DIR"
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        return 0  # Has changes
    fi
    if [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then
        return 0  # Has new files
    fi
    return 1  # No changes
}

check_circuit_breaker() {
    local iteration=$1
    local had_progress=$2  # "yes" or "no" - passed in by caller

    # Read current state
    local no_progress=$(jq -r '.no_progress_count' "$CB_FILE" 2>/dev/null || echo "0")

    if [ "$had_progress" = "yes" ]; then
        # Progress detected, reset circuit breaker
        echo "{\"state\":\"CLOSED\",\"no_progress_count\":0,\"last_progress_iteration\":$iteration}" > "$CB_FILE"
        echo -e "${GREEN}[CIRCUIT BREAKER]${NC} Progress detected, state: CLOSED"
        return 0
    else
        # No progress
        no_progress=$((no_progress + 1))

        if [ $no_progress -ge $CB_STOP_THRESHOLD ]; then
            echo "{\"state\":\"OPEN\",\"no_progress_count\":$no_progress,\"last_progress_iteration\":$iteration}" > "$CB_FILE"
            echo -e "${RED}[CIRCUIT BREAKER] OPEN - No progress for $no_progress iterations. Stopping loop.${NC}"
            return 1  # Signal to stop loop
        elif [ $no_progress -ge $CB_WARNING_THRESHOLD ]; then
            echo "{\"state\":\"HALF_OPEN\",\"no_progress_count\":$no_progress,\"last_progress_iteration\":$iteration}" > "$CB_FILE"
            echo -e "${YELLOW}[CIRCUIT BREAKER] WARNING - No progress for $no_progress iterations${NC}"
            return 0  # Continue but warn
        else
            echo "{\"state\":\"CLOSED\",\"no_progress_count\":$no_progress,\"last_progress_iteration\":$iteration}" > "$CB_FILE"
            echo -e "${CYAN}[CIRCUIT BREAKER]${NC} No changes this iteration (count: $no_progress)"
            return 0
        fi
    fi
}

#=============================================================================
# HEARTBEAT FUNCTIONS
#=============================================================================

check_heartbeat_stale() {
    local max_stale_minutes=${1:-$HEARTBEAT_STALE_MINUTES}

    if [ ! -f "$HEARTBEAT_FILE" ]; then
        return 0  # No heartbeat file yet, assume OK (just starting)
    fi

    local last_timestamp=$(jq -r '.timestamp' "$HEARTBEAT_FILE" 2>/dev/null)
    if [ -z "$last_timestamp" ] || [ "$last_timestamp" = "null" ]; then
        return 0  # Can't parse, assume OK
    fi

    # Parse ISO 8601 timestamp and compare with now
    # macOS date -j -f doesn't handle ISO 8601 well, so use a workaround
    local last_epoch
    # Try to extract just the datetime part and convert
    local datetime_part=$(echo "$last_timestamp" | sed 's/+.*//' | sed 's/T/ /')
    last_epoch=$(date -j -f "%Y-%m-%d %H:%M:%S" "$datetime_part" "+%s" 2>/dev/null || echo "0")

    if [ "$last_epoch" = "0" ]; then
        # Fallback: try stat on the file
        last_epoch=$(stat -f %m "$HEARTBEAT_FILE" 2>/dev/null || echo "0")
    fi

    local now_epoch=$(date "+%s")
    local diff_seconds=$((now_epoch - last_epoch))
    local diff_minutes=$((diff_seconds / 60))

    if [ $diff_minutes -ge $max_stale_minutes ]; then
        echo -e "${RED}[HEARTBEAT]${NC} Stale! Last update: $diff_minutes minutes ago"
        return 1  # Heartbeat is stale
    fi

    return 0  # Heartbeat is fresh
}

#=============================================================================
# ZOMBIE CLEANUP FUNCTION
#=============================================================================

cleanup_zombie_processes() {
    echo -e "${CYAN}[CLEANUP]${NC} Checking for zombie processes..."

    # Kill potentially stuck test servers
    local killed_count=0

    # Python server processes
    if pkill -f "python.*-m server.main" 2>/dev/null; then
        echo -e "${CYAN}[CLEANUP]${NC} Killed stuck server process"
        killed_count=$((killed_count + 1))
    fi

    # Stuck pytest processes
    if pkill -f "python.*pytest" 2>/dev/null; then
        echo -e "${CYAN}[CLEANUP]${NC} Killed stuck pytest process"
        killed_count=$((killed_count + 1))
    fi

    # Release port 8080 if occupied
    local port_pid=$(lsof -ti :8080 2>/dev/null || true)
    if [ -n "$port_pid" ]; then
        echo -e "${CYAN}[CLEANUP]${NC} Killing process on port 8080: $port_pid"
        kill -9 $port_pid 2>/dev/null || true
        killed_count=$((killed_count + 1))
    fi

    if [ $killed_count -gt 0 ]; then
        sleep 2  # Give processes time to clean up
    fi

    echo -e "${CYAN}[CLEANUP]${NC} Done (killed $killed_count processes)"
}

#=============================================================================
# AGENT RUNNER WITH HEARTBEAT MONITORING
#=============================================================================

kill_agent() {
    local pid=$1
    local agent_name=$2

    # Graceful kill first (SIGTERM)
    kill $pid 2>/dev/null || true
    sleep 5

    # Force kill if still alive (SIGKILL)
    if kill -0 $pid 2>/dev/null; then
        echo -e "${RED}[$agent_name]${NC} Force killing PID $pid"
        kill -9 $pid 2>/dev/null || true
    fi

    # Cleanup any zombies left behind
    cleanup_zombie_processes
}

run_agent_with_heartbeat() {
    local agent_name=$1
    local prompt=$2
    local log_file=$3
    local color=$4

    # Pre-flight cleanup
    cleanup_zombie_processes

    # Set agent name for heartbeat script
    export GENESIS_AGENT="$agent_name"

    # Clear old heartbeat
    rm -f "$HEARTBEAT_FILE"

    # Start Claude in background
    cd "$GENESIS_DIR"
    claude --dangerously-skip-permissions "$prompt" > "$log_file" 2>&1 &
    local claude_pid=$!
    local start_epoch=$(date "+%s")

    echo -e "${color}[$agent_name]${NC} Started with PID $claude_pid"
    echo -e "${color}[$agent_name]${NC} Log: $log_file"
    echo -e "${color}[$agent_name]${NC} Max runtime: ${AGENT_MAX_RUNTIME_MINUTES}min, heartbeat timeout: ${HEARTBEAT_STALE_MINUTES}min"

    # Monitor loop: check heartbeat while Claude is running
    while kill -0 $claude_pid 2>/dev/null; do
        sleep $HEARTBEAT_CHECK_INTERVAL

        # Check if Claude is still running (may have exited during sleep)
        if ! kill -0 $claude_pid 2>/dev/null; then
            break
        fi

        # Check total runtime cap (prevents infinite loops even with good heartbeat)
        local now_epoch=$(date "+%s")
        local elapsed_minutes=$(( (now_epoch - start_epoch) / 60 ))
        if [ $elapsed_minutes -ge $AGENT_MAX_RUNTIME_MINUTES ]; then
            echo -e "${YELLOW}[$agent_name] MAX RUNTIME (${AGENT_MAX_RUNTIME_MINUTES}min) reached - terminating${NC}"
            kill_agent $claude_pid "$agent_name"
            echo -e "${YELLOW}[$agent_name] Last 50 lines of log:${NC}"
            tail -50 "$log_file" 2>/dev/null || true
            return 125  # Exit code for max runtime
        fi

        # Check heartbeat (detects stuck-on-command state)
        if ! check_heartbeat_stale $HEARTBEAT_STALE_MINUTES; then
            echo -e "${RED}[$agent_name] STUCK - No heartbeat for ${HEARTBEAT_STALE_MINUTES}+ minutes${NC}"
            echo -e "${RED}[$agent_name] Terminating PID $claude_pid${NC}"
            kill_agent $claude_pid "$agent_name"
            echo -e "${RED}[$agent_name] Last 50 lines of log:${NC}"
            tail -50 "$log_file" 2>/dev/null || true
            return 124  # Exit code for heartbeat timeout
        fi

        echo -e "${color}[$agent_name]${NC} Heartbeat OK | ${elapsed_minutes}/${AGENT_MAX_RUNTIME_MINUTES}min"
    done

    # Wait for Claude to finish and get exit code
    wait $claude_pid 2>/dev/null
    local exit_code=$?

    # Show summary (not full log - log file is saved for later review)
    local now_epoch=$(date "+%s")
    local elapsed_minutes=$(( (now_epoch - start_epoch) / 60 ))
    echo -e "${color}[$agent_name]${NC} Completed in ${elapsed_minutes}min (exit code: $exit_code)"
    echo -e "${color}[$agent_name]${NC} Full log: $log_file"
    # Show just the tail for quick review
    echo -e "${color}[$agent_name] Last 30 lines:${NC}"
    tail -30 "$log_file" 2>/dev/null || true

    return $exit_code
}

#=============================================================================
# LEGACY AGENT RUNNERS (for comparison/fallback)
#=============================================================================

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping multi-agent loop...${NC}"
    echo "false" > "$LOOP_FLAG_FILE"
    cleanup_zombie_processes
    exit 0
}

trap cleanup SIGINT SIGTERM

# Check if there are issues needing verification
check_needs_verification() {
    cd "$GENESIS_DIR"
    local count=$(gh issue list --label "needs-verification" --state open --json number 2>/dev/null | jq length 2>/dev/null || echo "0")
    echo "$count"
}

# Check if there are any open issues (for Planner trigger)
check_open_issues() {
    cd "$GENESIS_DIR"
    local count=$(gh issue list --state open --json number 2>/dev/null | jq length 2>/dev/null || echo "0")
    echo "$count"
}

# Run Builder
run_builder() {
    local timestamp=$(date +%Y-%m-%d_%H%M%S)
    local log_file="$LOG_DIR/builder_$timestamp.log"

    local prompt="Use the builder agent to implement the highest priority issue.

         The builder agent will:
         1. Read claude_iteration/state.md and VISION.md for context
         2. Select highest priority open issue (critical > high > medium > low)
         3. Implement the feature or fix the bug
         4. Write tests for new code
         5. Add 'needs-verification' label when done
         6. Update state.md and write to runlog

         IMPORTANT:
         - Do NOT close issues - only Criticizer can do that
         - Do NOT modify VISION.md - that belongs to Planner
         - Focus on ONE issue per iteration"

    run_agent_with_heartbeat "Builder" "$prompt" "$log_file" "$GREEN"
    return $?
}

# Run Criticizer
run_criticizer() {
    local timestamp=$(date +%Y-%m-%d_%H%M%S)
    local log_file="$LOG_DIR/criticizer_$timestamp.log"

    local prompt="Use the criticizer agent to verify issues and provide insights.

         The criticizer agent will:
         1. Find issues with 'needs-verification' label
         2. Actually RUN the AI Assistant and test each acceptance criterion
         3. Close issues that pass (with verification report and evidence)
         4. Create bug issues for failures

         If no pending verifications, run discovery testing:
         - 对话流程测试 (context retention)
         - 功能集成测试 (file upload + query)
         - 恢复测试 (data persistence)
         - 异常输入测试 (edge cases)
         - 连续请求测试 (stability)

         IMPORTANT - Feedback to Planner:
         - Write insights to criticizer_iteration/insights_for_planner.md
         - Report: repeated bug patterns, test coverage gaps, UX issues
         - Update criticizer_iteration/state.md and verification_logs/"

    run_agent_with_heartbeat "Criticizer" "$prompt" "$log_file" "$YELLOW"
    return $?
}

# Run Planner
run_planner() {
    local timestamp=$(date +%Y-%m-%d_%H%M%S)
    local log_file="$LOG_DIR/planner_$timestamp.log"

    local prompt="Use the planner agent - you are the SOUL and CREATOR of Genesis.

         你是产品的灵魂。你不是工具，你是创造者。

         The planner agent will:
         1. Read VISION.md (you own this) and planner_iteration/state.md
         2. Read criticizer_iteration/insights_for_planner.md for feedback
         3. Reflect: Would users LOVE this product? What's missing?
         4. If ideas are exhausted, use WebSearch to research human needs:
            - What do users want from AI assistants?
            - What are competitors doing well?
            - What human needs can AI fulfill?
         5. Create/prioritize issues based on your judgment
         6. You CAN REFUSE any request that conflicts with product vision
         7. Update VISION.md if the vision evolves
         8. Update planner_iteration/state.md and roadmap.md

         唯一约束: 让 Genesis 成功 - 人人爱用，人人离不开。"

    run_agent_with_heartbeat "Planner" "$prompt" "$log_file" "$BLUE"
    return $?
}

# Git sync
git_sync() {
    cd "$GENESIS_DIR"

    if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
        echo "No changes to commit"
        return 0
    fi

    git add -A
    git commit -m "Auto-commit: Multi-agent iteration $ITERATION_COUNT - $(date '+%Y-%m-%d %H:%M')" --no-verify 2>/dev/null || true
    git push 2>/dev/null || echo "Push failed (will retry)"
}

#=============================================================================
# MAIN LOOP
#=============================================================================

main_loop() {
    # Initialize circuit breaker
    init_circuit_breaker

    while true; do
        # Check if loop should continue
        if [ -f "$LOOP_FLAG_FILE" ]; then
            local flag_value=$(cat "$LOOP_FLAG_FILE" 2>/dev/null | tr -d '[:space:]')
            if [ "$flag_value" != "true" ]; then
                echo -e "${RED}Loop flag is '$flag_value', stopping...${NC}"
                break
            fi
        else
            echo -e "${RED}Loop flag file not found, stopping...${NC}"
            break
        fi

        ITERATION_COUNT=$((ITERATION_COUNT + 1))
        echo ""
        echo -e "${BLUE}========================================${NC}"
        echo -e "${BLUE}   Iteration $ITERATION_COUNT - $(date '+%Y-%m-%d %H:%M:%S')${NC}"
        echo -e "${BLUE}========================================${NC}"

        # Track whether ANY phase made progress this iteration
        local iteration_progress="no"

        # Phase 1: Builder
        echo ""
        echo "--- Phase 1: Builder ---"
        local builder_exit=0
        run_builder || builder_exit=$?
        if [ $builder_exit -eq 124 ]; then
            echo -e "${YELLOW}[Builder]${NC} Timed out (heartbeat stale) - continuing to next phase"
        fi

        # Check for progress BEFORE git_sync (critical: git_sync commits everything, clearing the diff)
        if has_uncommitted_changes; then
            iteration_progress="yes"
        fi

        # Git sync after Builder
        echo ""
        echo "--- Git Sync ---"
        git_sync

        # Phase 2: Criticizer (if there are issues to verify)
        local needs_verify=$(check_needs_verification)
        if [ "$needs_verify" -gt 0 ]; then
            echo ""
            echo "--- Phase 2: Criticizer ($needs_verify issues to verify) ---"
            local criticizer_exit=0
            run_criticizer || criticizer_exit=$?
            if [ $criticizer_exit -eq 124 ]; then
                echo -e "${YELLOW}[Criticizer]${NC} Timed out (heartbeat stale) - continuing to next phase"
            fi

            # Check for progress BEFORE git_sync
            if has_uncommitted_changes; then
                iteration_progress="yes"
            fi

            # Git sync after Criticizer
            echo ""
            echo "--- Git Sync ---"
            git_sync
        else
            echo ""
            echo "--- Phase 2: Criticizer (skipped - no issues need verification) ---"
        fi

        # Phase 3: Planner (daily or when no open issues)
        local open_issues=$(check_open_issues)
        local run_planner_now=false

        # Run Planner if: no open issues OR every 5 iterations OR it's a new day
        if [ "$open_issues" -eq 0 ]; then
            echo ""
            echo "--- Phase 3: Planner (triggered: no open issues) ---"
            run_planner_now=true
        elif [ $((ITERATION_COUNT % 5)) -eq 0 ]; then
            echo ""
            echo "--- Phase 3: Planner (triggered: every 5 iterations) ---"
            run_planner_now=true
        fi

        if [ "$run_planner_now" = true ]; then
            local planner_exit=0
            run_planner || planner_exit=$?
            if [ $planner_exit -eq 124 ]; then
                echo -e "${YELLOW}[Planner]${NC} Timed out (heartbeat stale) - continuing to next phase"
            fi

            # Check for progress BEFORE git_sync
            if has_uncommitted_changes; then
                iteration_progress="yes"
            fi

            # Git sync after Planner
            echo ""
            echo "--- Git Sync ---"
            git_sync
        else
            echo ""
            echo "--- Phase 3: Planner (skipped - $open_issues open issues, iteration $ITERATION_COUNT) ---"
        fi

        # Check circuit breaker at end of iteration (uses progress flag, not git diff)
        echo ""
        echo "--- Circuit Breaker Check ---"
        if ! check_circuit_breaker $ITERATION_COUNT "$iteration_progress"; then
            echo -e "${RED}Circuit breaker tripped! Loop stopped.${NC}"
            break
        fi

        # Brief pause between iterations
        echo ""
        echo "Waiting 10 seconds before next iteration..."
        echo "(Set $LOOP_FLAG_FILE to 'false' to stop)"
        sleep 10
    done
}

# Start the loop
main_loop

echo ""
echo -e "${GREEN}Multi-agent loop stopped gracefully.${NC}"
cleanup_zombie_processes
