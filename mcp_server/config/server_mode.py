# SPDX-License-Identifier: MIT
#
"""
Server mode configuration for Librarian MCP Server.

Defines tool sets for different server modes (Admin, LibraryManager, LibraryUser).
"""

import os

SERVER_MODE = os.getenv("LIBRARIAN_SERVER_MODE", "Admin")

# LibraryManager mode: 18 tools (library management + search + CLI tools)
# Note: 3 task management tools may be implemented in later release
LIBRARYMANAGER_TOOLS = {
    # Library management
    "add_library",  # Create and index new library
    "delete_library",  # Delete library
    "list_libraries",  # List all libraries
    "get_library_stats",  # Get library statistics
    "sync_library_async",  # Incremental sync (background)
    "rebuild_library_async",  # Full rebuild (background)
    # Search tools
    "search_library",  # Semantic search
    "search_library_keyword",  # Keyword search
    "search_across_libraries",  # Cross-library search
    # Document access
    "list_library_documents",  # List indexed documents
    "read_library_document",  # Read document from library
    # Task management - MAY BE IMPLEMENTED IN LATER RELEASE to improve status on async tasks
    # "get_task_status",  # Check background task status
    # "get_task_logs",  # Get task logs
    # "list_recent_tasks",  # List recent tasks
    # CLI tools (full access for LibraryManager)
    "execute_command",  # Execute whitelisted commands
    "read_document",  # Read document from filesystem
    "list_documents",  # List documents in directory
    "search_documents",  # Search for text across documents
    "document_summary",  # Get document structure summary
    "write_document",  # ✅ AVAILABLE - Essential for LibraryUser workflow
    "server_info",  # Server information
}

# LibraryUser mode: 14 tools (read-only library access + CLI tools)
# Note: 3 task management tools may be implemented in later release
LIBRARYUSER_TOOLS = {
    # Read-only library tools
    "search_library",  # Semantic search
    "search_library_keyword",  # Keyword search
    "search_across_libraries",  # Cross-library search
    "list_libraries",  # List all libraries
    "get_library_stats",  # Get library statistics
    "list_library_documents",  # List indexed documents
    "read_library_document",  # Read document from library
    # Task management - MAY BE IMPLEMENTED IN LATER RELEASE to improve status on async tasks
    # "get_task_status",  # Check background task status
    # "get_task_logs",  # Get task logs
    # "list_recent_tasks",  # List recent tasks
    # CLI tools
    "execute_command",  # Execute whitelisted commands
    "read_document",  # Read document from filesystem
    "list_documents",  # List documents in directory
    "search_documents",  # Search for text across documents
    "document_summary",  # Get document structure summary
    "write_document",  # Write reports
    "server_info",  # Server information
}

# Admin mode: all tools (LibraryManager + LibraryUser + admin-only)
ADMIN_TOOLS = (
    LIBRARYMANAGER_TOOLS
    | LIBRARYUSER_TOOLS
    | {
        "admin_command",  # Developer debugging tool (Admin only)
    }
)


def get_tools_for_mode(mode: str = "Admin") -> set:
    if mode == "LibraryManager":
        return LIBRARYMANAGER_TOOLS
    elif mode == "LibraryUser":
        return LIBRARYUSER_TOOLS
    else:  # "Admin"
        return ADMIN_TOOLS
