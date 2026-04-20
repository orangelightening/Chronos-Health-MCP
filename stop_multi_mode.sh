#!/bin/bash
#
# Librarian MCP Multi-Mode Server Stop Script
#
# Stops all three server instances started by start_multi_mode.sh
# Also kills any orphaned librarian_mcp.py processes
#
# Usage:
#   ./stop_multi_mode.sh

echo "Stopping Librarian MCP servers..."

# Function to stop a server
stop_server() {
    local name=$1
    local pid_file=$2

    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Stopping $name server (PID: $PID)..."
            kill "$PID" 2>/dev/null

            # Wait for process to terminate (max 5 seconds)
            for i in {1..5}; do
                if ! kill -0 "$PID" 2>/dev/null; then
                    break
                fi
                sleep 1
            done

            # Force kill if still running
            if kill -0 "$PID" 2>/dev/null; then
                echo "  Force killing $name server..."
                kill -9 "$PID" 2>/dev/null
            fi

            echo "  ✓ $name server stopped"
        else
            echo "  ⚠ $name server is not running (stale PID file)"
        fi
        rm -f "$pid_file" 2>/dev/null || true
    else
        echo "  - $name server PID file not found"
    fi
}

# Stop all three servers using PID files
stop_server "LibraryManager" "/tmp/librarian-LibraryManager.pid"
stop_server "LibraryUser" "/tmp/librarian-LibraryUser.pid"
stop_server "Admin" "/tmp/librarian-Admin.pid"

# Fallback: Kill any remaining librarian_mcp.py processes by port
echo ""
echo "Checking for orphaned processes..."

# Check ports 8889, 8890, 8891
for port in 8889 8890 8891; do
    PID=$(lsof -t -i:$port 2>/dev/null | head -1)
    if [ -n "$PID" ]; then
        echo "  Found orphaned process on port $port (PID: $PID), killing..."
        kill -9 "$PID" 2>/dev/null
    fi
done

# Also check for any librarian_mcp.py processes that might be running
PIDS=$(ps aux | grep '[l]ibrarian_mcp.py' | awk '{print $2}')
if [ -n "$PIDS" ]; then
    echo "  Found remaining librarian_mcp.py processes: $PIDS"
    echo "  Killing them..."
    kill -9 $PIDS 2>/dev/null
fi

echo ""
echo "All servers stopped."
echo "Logs are still available at:"
echo "  /tmp/librarian-LibraryManager.log"
echo "  /tmp/librarian-LibraryUser.log"
echo "  /tmp/librarian-Admin.log"
