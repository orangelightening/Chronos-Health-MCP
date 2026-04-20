#!/bin/bash
#
# Librarian MCP Multi-Mode Server Startup Script
#
# Starts three server instances simultaneously:
# - LibraryManager mode (18 tools) on port 8889
# - LibraryUser mode (13 tools) on port 8890
# - Admin mode (18 tools) on port 8891

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🧹 Clearing Python bytecode cache..."
find "$SCRIPT_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find "$SCRIPT_DIR/mcp_server" -name "*.pyc" -delete 2>/dev/null
echo "✅ Cache cleared"

# Disable Python bytecode caching for development
export PYTHONDONTWRITEBYTECODE=1

# Default ports
LIBRARYMANAGER_PORT=8889
LIBRARYUSER_PORT=8890
ADMIN_PORT=8891

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --librarymanager-port) LIBRARYMANAGER_PORT="$2"; shift 2 ;;
        --libraryuser-port) LIBRARYUSER_PORT="$2"; shift 2 ;;
        --admin-port) ADMIN_PORT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Check for running servers
for mode in LibraryManager LibraryUser Admin; do
    pid_file="/tmp/librarian-${mode}.pid"
    if [ -f "$pid_file" ] && kill -0 $(cat "$pid_file") 2>/dev/null; then
        echo "Error: ${mode} server already running (PID: $(cat $pid_file))"
        echo "Use ./stop_multi_mode.sh first"
        exit 1
    fi
done

# Activate venv
if [ -d "${SCRIPT_DIR}/venv" ]; then
    source "${SCRIPT_DIR}/venv/bin/activate"
    PYTHON_CMD="${SCRIPT_DIR}/venv/bin/python"
else
    echo "Error: No virtual environment at ${SCRIPT_DIR}/venv"
    exit 1
fi

export PYTHONPATH="${SCRIPT_DIR}:$PYTHONPATH"

echo "Starting multi-mode Librarian MCP Server..."
echo "  LibraryManager: http://localhost:${LIBRARYMANAGER_PORT} (18 tools)"
echo "  LibraryUser:    http://localhost:${LIBRARYUSER_PORT} (13 tools)"
echo "  Admin:          http://localhost:${ADMIN_PORT} (All tools)"
echo ""

# Start LibraryManager
LIBRARIAN_SERVER_MODE=LibraryManager "$PYTHON_CMD" "${SCRIPT_DIR}/mcp_server/librarian_mcp.py" \
    --transport http --host 0.0.0.0 --port "${LIBRARYMANAGER_PORT}" >/tmp/librarian-LibraryManager.log 2>&1 &
echo $! > /tmp/librarian-LibraryManager.pid
echo "Started LibraryManager (PID: $!)"

# Start LibraryUser
LIBRARIAN_SERVER_MODE=LibraryUser "$PYTHON_CMD" "${SCRIPT_DIR}/mcp_server/librarian_mcp.py" \
    --transport http --host 0.0.0.0 --port "${LIBRARYUSER_PORT}" >/tmp/librarian-LibraryUser.log 2>&1 &
echo $! > /tmp/librarian-LibraryUser.pid
echo "Started LibraryUser (PID: $!)"

# Start Admin
LIBRARIAN_SERVER_MODE=Admin "$PYTHON_CMD" "${SCRIPT_DIR}/mcp_server/librarian_mcp.py" \
    --transport http --host 0.0.0.0 --port "${ADMIN_PORT}" >/tmp/librarian-Admin.log 2>&1 &
echo $! > /tmp/librarian-Admin.pid
echo "Started Admin (PID: $!)"

echo ""
echo "Waiting for servers to start..."
sleep 5

echo ""
echo "Health check:"
for port_info in "${LIBRARYMANAGER_PORT}:LibraryManager" "${LIBRARYUSER_PORT}:LibraryUser" "${ADMIN_PORT}:Admin"; do
    port="${port_info%%:*}"
    name="${port_info##*:}"
    # Check if port is listening (MCP uses POST, not GET)
    if nc -z localhost "$port" 2>/dev/null; then
        echo "  ✓ ${name} server running on port ${port}"
    else
        echo "  ✗ ${name} server FAILED on port ${port}"
    fi
done

echo ""
echo "Logs: /tmp/librarian-*.log"
echo "Stop: ./stop_multi_mode.sh"
echo ""
echo "💡 To verify code is loaded: ./verify_sync_code.sh"
