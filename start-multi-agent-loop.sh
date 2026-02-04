#!/bin/bash
# Genesis Multi-Agent Loop
# Coordinates Builder -> Criticizer -> Planner

set -e

GENESIS_DIR="/Volumes/Storage/Server/Startup/Genesis"
LOOP_FLAG_FILE="$GENESIS_DIR/hooks/loop_multi_agent.txt"
LOG_DIR="$GENESIS_DIR/orchestration_logs"
ITERATION_COUNT=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create log directory
mkdir -p "$LOG_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Genesis Multi-Agent Loop Starting   ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Project: $GENESIS_DIR"
echo "Logs: $LOG_DIR"
echo "Stop: Create $LOOP_FLAG_FILE with content 'false' or Ctrl+C"
echo ""

# Initialize loop flag
echo "true" > "$LOOP_FLAG_FILE"

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping multi-agent loop...${NC}"
    echo "false" > "$LOOP_FLAG_FILE"
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

    echo -e "${GREEN}[Builder]${NC} Starting iteration..."
    echo "[Builder] Log: $log_file"

    cd "$GENESIS_DIR"

    # Run Builder (Claude Code with standard rules)
    claude --dangerously-skip-permissions \
        "Execute one iteration per the contract in CLAUDE.md.
         IMPORTANT: You are the BUILDER.
         - Check GitHub Issues first (priority-critical > priority-high > oldest)
         - If you complete an issue, add 'needs-verification' label and comment with test instructions
         - Do NOT close issues - only Criticizer can do that
         - Read claude_iteration/state.md for context
         - Update state.md and write to runlog when done" \
        2>&1 | tee "$log_file"

    local exit_code=${PIPESTATUS[0]}
    echo -e "${GREEN}[Builder]${NC} Completed with exit code: $exit_code"
    return $exit_code
}

# Run Criticizer
run_criticizer() {
    local timestamp=$(date +%Y-%m-%d_%H%M%S)
    local log_file="$LOG_DIR/criticizer_$timestamp.log"

    echo -e "${YELLOW}[Criticizer]${NC} Starting verification..."
    echo "[Criticizer] Log: $log_file"

    cd "$GENESIS_DIR"

    # Run Criticizer subagent
    claude --dangerously-skip-permissions \
        "Use the criticizer agent to verify all issues with the 'needs-verification' label.

         The criticizer agent will:
         1. Find issues with needs-verification label
         2. Actually run the AI Assistant and test each acceptance criterion
         3. Close issues that pass (with verification report)
         4. Create bug issues for failures
         5. Run discovery testing if no pending verifications
         6. Update criticizer_iteration/state.md" \
        2>&1 | tee "$log_file"

    local exit_code=${PIPESTATUS[0]}
    echo -e "${YELLOW}[Criticizer]${NC} Completed with exit code: $exit_code"
    return $exit_code
}

# Run Planner
run_planner() {
    local timestamp=$(date +%Y-%m-%d_%H%M%S)
    local log_file="$LOG_DIR/planner_$timestamp.log"

    echo -e "${BLUE}[Planner]${NC} Starting strategic review..."
    echo "[Planner] Log: $log_file"

    cd "$GENESIS_DIR"

    # Run Planner subagent
    claude --dangerously-skip-permissions \
        "Use the planner agent to review the project status and update priorities.

         The planner agent will:
         1. Gather context from all state files
         2. Check progress against roadmap
         3. Identify patterns and technical debt
         4. Update priorities on issues
         5. Create new strategic issues if needed
         6. Update planner_iteration/state.md and roadmap.md" \
        2>&1 | tee "$log_file"

    local exit_code=${PIPESTATUS[0]}
    echo -e "${BLUE}[Planner]${NC} Completed with exit code: $exit_code"
    return $exit_code
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

# Main loop
main_loop() {
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

        # Phase 1: Builder
        echo ""
        echo "--- Phase 1: Builder ---"
        run_builder || true

        # Git sync after Builder
        echo ""
        echo "--- Git Sync ---"
        git_sync

        # Phase 2: Criticizer (if there are issues to verify)
        local needs_verify=$(check_needs_verification)
        if [ "$needs_verify" -gt 0 ]; then
            echo ""
            echo "--- Phase 2: Criticizer ($needs_verify issues to verify) ---"
            run_criticizer || true

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
            run_planner || true

            # Git sync after Planner
            echo ""
            echo "--- Git Sync ---"
            git_sync
        else
            echo ""
            echo "--- Phase 3: Planner (skipped - $open_issues open issues, iteration $ITERATION_COUNT) ---"
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
