#!/bin/bash
# Genesis AI Assistant - Service Management Script
# Uses Supervisor for cross-platform compatibility
# Usage: ./assistant-service.sh [install|uninstall|start|stop|restart|status|logs]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ASSISTANT_DIR="$(dirname "$SCRIPT_DIR")"
GENESIS_DIR="$(dirname "$ASSISTANT_DIR")"
SUPERVISOR_CONF="$SCRIPT_DIR/supervisord.conf"
LOG_DIR="$HOME/Library/Logs/Genesis"
SOCK_FILE="/tmp/genesis-supervisor.sock"
PID_FILE="/tmp/genesis-supervisord.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if supervisor is installed
check_supervisor() {
    if ! command -v supervisord &> /dev/null; then
        echo -e "${RED}ERROR: supervisord not found${NC}"
        echo "Install with: pip install supervisor"
        echo "Or: brew install supervisor"
        exit 1
    fi
}

# Install/setup the service
install_service() {
    echo "Setting up Genesis AI Assistant service..."
    check_supervisor

    # Create log directory
    mkdir -p "$LOG_DIR"
    echo -e "${GREEN}Log directory: $LOG_DIR${NC}"

    # Update config with correct paths
    echo "Supervisor config: $SUPERVISOR_CONF"
    echo ""
    echo -e "${GREEN}Installation complete!${NC}"
    echo "Run './assistant-service.sh start' to start the service"
}

# Uninstall the service
uninstall_service() {
    echo "Stopping and cleaning up Genesis AI Assistant service..."

    # Stop supervisor if running
    if [ -S "$SOCK_FILE" ]; then
        supervisorctl -c "$SUPERVISOR_CONF" shutdown 2>/dev/null || true
    fi

    # Remove pid file
    rm -f "$PID_FILE"
    rm -f "$SOCK_FILE"

    echo -e "${GREEN}Service stopped. Logs remain at: $LOG_DIR/${NC}"
}

# Start the service
start_service() {
    check_supervisor

    if [ -S "$SOCK_FILE" ]; then
        echo -e "${YELLOW}Supervisor already running. Starting assistant...${NC}"
        supervisorctl -c "$SUPERVISOR_CONF" start assistant
    else
        echo "Starting Supervisor daemon..."
        mkdir -p "$LOG_DIR"

        # Export required environment variables
        export HOME="$HOME"
        export GENESIS_DIR="$GENESIS_DIR"

        supervisord -c "$SUPERVISOR_CONF"
        sleep 2
    fi

    show_status
}

# Stop the service
stop_service() {
    echo "Stopping Genesis AI Assistant..."

    if [ -S "$SOCK_FILE" ]; then
        supervisorctl -c "$SUPERVISOR_CONF" stop assistant 2>/dev/null || true
        echo -e "${GREEN}Assistant stopped${NC}"
    else
        echo -e "${YELLOW}Supervisor not running${NC}"
    fi
}

# Stop supervisor daemon completely
shutdown_service() {
    echo "Shutting down Supervisor daemon..."

    if [ -S "$SOCK_FILE" ]; then
        supervisorctl -c "$SUPERVISOR_CONF" shutdown
        echo -e "${GREEN}Supervisor shutdown complete${NC}"
    else
        echo -e "${YELLOW}Supervisor not running${NC}"
    fi
}

# Restart the service
restart_service() {
    echo "Restarting Genesis AI Assistant..."

    if [ -S "$SOCK_FILE" ]; then
        supervisorctl -c "$SUPERVISOR_CONF" restart assistant
    else
        echo -e "${YELLOW}Supervisor not running. Starting...${NC}"
        start_service
    fi

    sleep 2
    show_status
}

# Show service status
show_status() {
    echo "=== Genesis AI Assistant Status ==="
    echo ""

    if [ -S "$SOCK_FILE" ]; then
        echo -e "${GREEN}Supervisor: RUNNING${NC}"
        supervisorctl -c "$SUPERVISOR_CONF" status assistant
    else
        echo -e "${RED}Supervisor: NOT RUNNING${NC}"
    fi

    echo ""
    echo "Checking if server is responding..."
    if curl -s "http://127.0.0.1:8080/api/health" 2>/dev/null; then
        echo ""
        echo -e "${GREEN}HTTP: OK (http://127.0.0.1:8080)${NC}"
    else
        echo -e "${RED}HTTP: NOT RESPONDING${NC}"
    fi
}

# Show logs
show_logs() {
    echo "=== Recent Logs ==="
    echo ""

    if [ -S "$SOCK_FILE" ]; then
        echo "--- Live tail (Ctrl+C to exit) ---"
        supervisorctl -c "$SUPERVISOR_CONF" tail -f assistant
    else
        if [ -f "$LOG_DIR/assistant.out.log" ]; then
            echo "--- stdout (last 30 lines) ---"
            tail -30 "$LOG_DIR/assistant.out.log"
        fi
        echo ""
        if [ -f "$LOG_DIR/assistant.err.log" ]; then
            echo "--- stderr (last 30 lines) ---"
            tail -30 "$LOG_DIR/assistant.err.log"
        fi
    fi
}

# Main
case "${1:-}" in
    install)
        install_service
        ;;
    uninstall)
        uninstall_service
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    shutdown)
        shutdown_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Genesis AI Assistant - Service Manager (Supervisor)"
        echo ""
        echo "Usage: $0 {install|uninstall|start|stop|shutdown|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  install   - Set up the service (creates log directory)"
        echo "  uninstall - Stop and clean up the service"
        echo "  start     - Start the Supervisor daemon and assistant"
        echo "  stop      - Stop the assistant (keeps Supervisor running)"
        echo "  shutdown  - Stop everything including Supervisor daemon"
        echo "  restart   - Restart the assistant"
        echo "  status    - Show service status"
        echo "  logs      - Show/tail log output"
        echo ""
        echo "Prerequisites:"
        echo "  pip install supervisor"
        echo "  # or: brew install supervisor"
        exit 1
        ;;
esac
