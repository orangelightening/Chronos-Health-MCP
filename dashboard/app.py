# SPDX-License-Identifier: MIT
#
"""
Chronos Health Dashboard — Read-only status page.

A standalone FastAPI app on port 8892 that shows server and library status.
Separate from the MCP servers — serves humans, not AI clients.
"""

import os
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Import shared core classes (same ones the MCP tools use)
from mcp_server.core.library_manager import LibraryManager
from mcp_server.core.library_status import LibraryStatus


app = FastAPI(title="Chronos Health Dashboard")

# Serve static files (style.css, etc.)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _get_server_status():
    """Check all three MCP server modes via PID files."""
    servers = []
    for mode, port in [("LibraryManager", 8889), ("LibraryUser", 8890), ("Admin", 8891)]:
        pid_file = f"/tmp/librarian-{mode}.pid"
        running = False
        uptime_seconds = None

        if os.path.exists(pid_file):
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                # Check if process is alive
                os.kill(pid, 0)
                running = True
                # Calculate uptime from PID file modification time
                uptime_seconds = int(time.time() - os.path.getmtime(pid_file))
            except (ProcessLookupError, PermissionError, ValueError, OSError):
                running = False

        servers.append({
            "mode": mode,
            "port": port,
            "running": running,
            "uptime_seconds": uptime_seconds,
        })
    return servers


def _format_uptime(seconds):
    """Format seconds into human-readable uptime string."""
    if seconds is None:
        return None
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours < 24:
        return f"{hours}h {remaining_minutes}m"
    days = hours // 24
    remaining_hours = hours % 24
    return f"{days}d {remaining_hours}h"


def _get_library_status():
    """Get status for all registered libraries."""
    try:
        manager = LibraryManager()
        libraries = manager.list_libraries()
        broken = manager.get_broken_libraries()
    except Exception:
        # Graceful degradation — return empty if LibraryManager fails
        return []

    results = []
    for lib in libraries:
        name = lib.get("name", "unknown")
        path = lib.get("path", "unknown")
        description = lib.get("description", "")

        # Check if broken
        if name in broken:
            results.append({
                "name": name,
                "path": path,
                "description": description,
                "status": "broken",
                "error": f"Path does not exist: {broken[name]}",
                "documents": None,
                "chunks": None,
                "last_sync": None,
                "syncing": False,
            })
            continue

        # Read library config for stats
        try:
            config = manager.get_library_config(name)
            status_info = config.get("status", {}) if config else {}

            # Check if currently syncing
            lib_path = Path(path)
            ls = LibraryStatus(lib_path)
            syncing = ls.is_active()

            results.append({
                "name": name,
                "path": path,
                "description": description,
                "status": "ok",
                "error": None,
                "documents": status_info.get("document_count", 0),
                "chunks": status_info.get("chunk_count", 0),
                "last_sync": status_info.get("last_sync", "Never"),
                "syncing": syncing,
            })
        except Exception as e:
            # Library exists but couldn't read config
            results.append({
                "name": name,
                "path": path,
                "description": description,
                "status": "error",
                "error": str(e),
                "documents": None,
                "chunks": None,
                "last_sync": None,
                "syncing": False,
            })

    return results


@app.get("/")
async def root():
    """Serve the dashboard HTML page."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/status")
async def get_status():
    """Combined status: servers + libraries."""
    servers = _get_server_status()
    libraries = _get_library_status()

    # Format uptime for display
    for server in servers:
        server["uptime"] = _format_uptime(server.pop("uptime_seconds"))

    return {
        "servers": servers,
        "libraries": libraries,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/servers")
async def get_servers():
    """Server status only."""
    servers = _get_server_status()
    for server in servers:
        server["uptime"] = _format_uptime(server.pop("uptime_seconds"))
    return {"servers": servers, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}


@app.get("/api/libraries")
async def get_libraries():
    """Library status only."""
    libraries = _get_library_status()
    return {"libraries": libraries, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", "8892"))
    uvicorn.run(app, host="0.0.0.0", port=port)
