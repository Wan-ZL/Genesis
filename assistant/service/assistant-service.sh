#!/bin/bash
# Genesis AI Assistant - Service Management Script for macOS
# Usage: ./assistant-service.sh [install|uninstall|start|stop|restart|status|logs]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ASSISTANT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="com.genesis.assistant"
PLIST_TEMPLATE="$SCRIPT_DIR/$SERVICE_NAME.plist"
PLIST_INSTALLED="$HOME/Library/LaunchAgents/$SERVICE_NAME.plist"
LOG_DIR="$HOME/Library/Logs/Genesis"

# Find Python path
find_python() {
    if command -v python3 &> /dev/null; then
        python3 -c "import sys; print(sys.executable)"
    else
        echo "ERROR: python3 not found" >&2
        exit 1
    fi
}

# Install the service
install_service() {
    echo "Installing Genesis AI Assistant service..."

    PYTHON_PATH=$(find_python)
    echo "Using Python: $PYTHON_PATH"
    echo "Assistant directory: $ASSISTANT_DIR"

    # Create log directory
    mkdir -p "$LOG_DIR"

    # Create LaunchAgents directory if needed
    mkdir -p "$HOME/Library/LaunchAgents"

    # Generate plist from template with paths substituted
    sed -e "s|__PYTHON_PATH__|$PYTHON_PATH|g" \
        -e "s|__ASSISTANT_DIR__|$ASSISTANT_DIR|g" \
        -e "s|__LOG_DIR__|$LOG_DIR|g" \
        "$PLIST_TEMPLATE" > "$PLIST_INSTALLED"

    echo "Plist installed to: $PLIST_INSTALLED"
    echo "Logs will be at: $LOG_DIR/"
    echo ""
    echo "Run './assistant-service.sh start' to start the service"
}

# Uninstall the service
uninstall_service() {
    echo "Uninstalling Genesis AI Assistant service..."

    # Stop if running
    if launchctl list | grep -q "$SERVICE_NAME"; then
        launchctl unload "$PLIST_INSTALLED" 2>/dev/null || true
    fi

    # Remove plist
    if [ -f "$PLIST_INSTALLED" ]; then
        rm "$PLIST_INSTALLED"
        echo "Removed: $PLIST_INSTALLED"
    fi

    echo "Service uninstalled. Logs remain at: $LOG_DIR/"
}

# Start the service
start_service() {
    if [ ! -f "$PLIST_INSTALLED" ]; then
        echo "Service not installed. Run './assistant-service.sh install' first."
        exit 1
    fi

    echo "Starting Genesis AI Assistant..."
    launchctl load "$PLIST_INSTALLED"
    sleep 2
    show_status
}

# Stop the service
stop_service() {
    echo "Stopping Genesis AI Assistant..."
    launchctl unload "$PLIST_INSTALLED" 2>/dev/null || echo "Service was not running"
}

# Restart the service
restart_service() {
    stop_service
    sleep 1
    start_service
}

# Show service status
show_status() {
    echo "=== Genesis AI Assistant Status ==="
    echo ""

    if launchctl list | grep -q "$SERVICE_NAME"; then
        echo "Service: RUNNING"
        launchctl list "$SERVICE_NAME" 2>/dev/null || true
    else
        echo "Service: STOPPED"
    fi

    echo ""
    echo "Checking if server is responding..."
    if curl -s "http://127.0.0.1:8080/api/health" > /dev/null 2>&1; then
        echo "HTTP: OK (http://127.0.0.1:8080)"
    elif curl -s "http://127.0.0.1:8080/" > /dev/null 2>&1; then
        echo "HTTP: OK (http://127.0.0.1:8080)"
    else
        echo "HTTP: NOT RESPONDING"
    fi
}

# Show logs
show_logs() {
    echo "=== Recent Logs ==="
    echo ""
    if [ -f "$LOG_DIR/assistant.out.log" ]; then
        echo "--- stdout (last 20 lines) ---"
        tail -20 "$LOG_DIR/assistant.out.log"
    fi
    echo ""
    if [ -f "$LOG_DIR/assistant.err.log" ]; then
        echo "--- stderr (last 20 lines) ---"
        tail -20 "$LOG_DIR/assistant.err.log"
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
        echo "Genesis AI Assistant - Service Manager"
        echo ""
        echo "Usage: $0 {install|uninstall|start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  install   - Install the launchd service (runs at login)"
        echo "  uninstall - Remove the launchd service"
        echo "  start     - Start the service"
        echo "  stop      - Stop the service"
        echo "  restart   - Restart the service"
        echo "  status    - Show service status"
        echo "  logs      - Show recent log output"
        exit 1
        ;;
esac
