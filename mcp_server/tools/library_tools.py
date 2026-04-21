# SPDX-License-Identifier: MIT
#
"""
Library tools for the Librarian MCP Server - Blue Sky Architecture

This module provides MCP tools for library management and search operations
using the new in-place indexing architecture (no shadow mode).

Key Changes from Shadow-Based Architecture:
- Libraries are indexed in-place (no shadow copies)
- Per-library ChromaDB instances
- Manual sync only (auto-sync deferred to 1.1)
- Async operations for long-running tasks (sync, rebuild, add)
- Synchronous operations for fast tasks (delete, list, search)
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Import new core components
from ..core.library_manager import LibraryManager
from ..core.indexer import Indexer
from ..core.library_status import LibraryStatus
from ..core.chromadb_orchestrator import ChromaDBOrchestrator

# ReportDelivery removed - using unified write_document instead
from .keyword_search import keyword_search

# Lazy initialization of core components
_library_manager = None
_chromadb_orchestrator = None


def get_library_manager():
    """Get or create LibraryManager instance."""
    global _library_manager
    if _library_manager is None:
        _library_manager = LibraryManager()
    return _library_manager


def get_chromadb_orchestrator():
    """Get or create ChromaDBOrchestrator instance."""
    global _chromadb_orchestrator
    if _chromadb_orchestrator is None:
        _chromadb_orchestrator = ChromaDBOrchestrator(get_library_manager())
    return _chromadb_orchestrator


# ============================================================================
# CLI TOOLS CONSTANTS (from cli_tools.py)
# ============================================================================

LIBRARIAN_WRITE_DIR = ".librarian"  # Subdirectory for write operations
MAX_OUTPUT_CHARS = 8000
DEFAULT_TIMEOUT_SECONDS = 15
MAX_WRITE_FILE_SIZE = 100000  # 100KB max for write operations

ALLOWED_BINARY_NAMES = {
    "ls",
    "cd",
    "pwd",
    "whoami",
    "echo",
    "cat",
    "find",
    "grep",
    "head",
    "tail",
    "sort",
    "uniq",
    "cut",
    "awk",
    "date",
    "hostname",
    "test",
    "mkdir",
    "wc",
    "diff",
    "stat",
    "file",
    "tree",
}

BANNED_FLAG_COMBOS = {
    ("find", "-delete"),
    ("find", "-exec"),
    ("find", "-execdir"),
    ("awk", "system"),
    ("awk", "systime"),
}

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".md",
    ".txt",
    ".py",
    ".js",
    ".ts",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".rst",
    ".html",
}

DANGEROUS_COMMANDS = {
    "rm",
    "rmdir",
    "chmod",
    "chown",
    "dd",
    "mkfs",
    "fdisk",
    "wget",
    "curl",
    "nc",
    "netcat",
    "ssh",
    "scp",
    "rsync",
    "tar",
    "zip",
    "unzip",
    "mount",
    "umount",
    "python",
    "python3",
    "perl",
    "bash",
    "sh",
    "zsh",
}

# ============================================================================
# ADMIN-ONLY COMMAND CONSTANTS
# ============================================================================

# Admin command whitelist — superset of execute_command's ALLOWED_BINARY_NAMES
# plus admin-only development/debugging commands.
# In admin mode, admin_command handles everything; execute_command is also
# available for testing purposes but is not needed for daily use.
ADMIN_BINARY_NAMES = {
    # Standard file inspection (same as execute_command)
    "ls",
    "cd",
    "pwd",
    "whoami",
    "echo",
    "cat",
    "find",
    "grep",
    "head",
    "tail",
    "sort",
    "uniq",
    "cut",
    "awk",
    "date",
    "hostname",
    "test",
    "mkdir",
    "wc",
    "diff",
    "stat",
    "file",
    "tree",
    # Admin-only additions
    "ps",  # Process inspection (read-only flags only)
    "pip",  # Dependency verification (list/show/search only)
    "env",  # Dump all environment variables
    "printenv",  # Print specific environment variable
    "which",  # Locate a command binary
}

# Arguments that turn read-only commands into write commands
ADMIN_WRITE_ARG_PATTERNS = {
    "pip": {"install", "uninstall", "download", "freeze"},
}

# ps flags that modify process state (block these)
PS_WRITE_FLAGS = {"-k", "-s", "--signal", "--session", "-r", "--reset"}


# ============================================================================
# CLI TOOLS HELPER FUNCTIONS
# ============================================================================


def is_safe_command(cmd: str, args: list) -> tuple[bool, str]:
    """Validate command against whitelist and banned flag combinations."""
    cmd_name = os.path.basename(cmd)

    if cmd_name in DANGEROUS_COMMANDS:
        return False, f"Command '{cmd_name}' is explicitly blocked."

    if cmd.startswith("/"):
        binary_name = os.path.basename(cmd)
        if binary_name in DANGEROUS_COMMANDS:
            return False, f"Binary '{binary_name}' is explicitly blocked."
    else:
        if cmd_name not in ALLOWED_BINARY_NAMES:
            return False, f"Command '{cmd_name}' is not in the allowed list."

    args_str = " ".join(args)
    for banned_cmd, banned_flag in BANNED_FLAG_COMBOS:
        if cmd_name == banned_cmd and banned_flag in args_str:
            return False, f"Flag '{banned_flag}' is not permitted with '{banned_cmd}'."

    return True, "OK"


def is_library_path(path: str) -> tuple[bool, str]:
    """Check that a path falls within a registered library root.

    This is the Blue Sky security boundary for CLI tools. A path is
    allowed only if it resolves inside one of the registered library
    directories (e.g., /home/peter/botany/, /home/peter/martha-health/).

    Args:
        path: File or directory path to validate (absolute or relative)

    Returns:
        (True, resolved_path) if path is within a library root
        (False, error_message) if path is outside all library roots
    """
    manager = get_library_manager()
    libraries = manager.list_libraries()

    if not libraries:
        return False, "No libraries registered. Use add_library() first."

    # Resolve the input path to an absolute path
    if os.path.isabs(path):
        resolved = os.path.realpath(path)
    else:
        # Relative paths are ambiguous without a base — reject them
        return False, (
            f"Relative path '{path}' is not allowed. "
            f"Use an absolute path like '/home/peter/botany/plants/oak.md'"
        )

    # Check against each registered library root
    for lib in libraries:
        lib_root = os.path.realpath(lib["path"])
        if resolved.startswith(lib_root + os.sep) or resolved == lib_root:
            return True, resolved

    # Not inside any library
    lib_paths = ", ".join(lib["path"] for lib in libraries[:5])
    return False, (
        f"Path '{path}' is outside all registered library roots. Registered: {lib_paths}"
    )


def truncate_output(text: str, limit: int = None) -> str:
    """Truncate output to protect LLM context window."""
    max_chars = limit if limit is not None else MAX_OUTPUT_CHARS
    if len(text) > max_chars:
        return text[:max_chars] + f"\n[output truncated — exceeded {max_chars} chars]"
    return text


def is_admin_path(path: str) -> tuple[bool, str]:
    """Check that path falls within a library root OR the project source directory.

    This is the expanded security boundary for admin_command only.
    execute_command continues to use is_library_path() exclusively.

    Args:
        path: File or directory path to validate (absolute or relative)

    Returns:
        (True, resolved_path) if path is within an allowed directory
        (False, error_message) if path is outside all allowed directories
    """
    # First check library paths (existing logic)
    safe, resolved = is_library_path(path)
    if safe:
        return True, resolved

    # Also allow project source directory
    from ..config.settings import settings

    project_root = str(settings.PROJECT_ROOT.resolve())

    if os.path.isabs(path):
        resolved = os.path.realpath(path)
    else:
        return False, (
            f"Relative path '{path}' is not allowed. Use an absolute path like '{project_root}'"
        )

    if resolved.startswith(project_root + os.sep) or resolved == project_root:
        return True, resolved

    return False, (
        f"Path '{path}' is outside both library roots and project directory. "
        f"Project: {project_root}"
    )


def is_safe_admin_command(cmd: str, args: list) -> tuple[bool, str]:
    """Validate admin command against superset whitelist and all guards.

    Admin commands include everything execute_command supports, plus
    admin-only development tools (ps, pip, env, printenv, which).
    All commands are read-only observation — argument guards block
    write-mode invocations.
    """
    cmd_name = os.path.basename(cmd)

    # Block explicitly dangerous commands (same as execute_command)
    if cmd_name in DANGEROUS_COMMANDS:
        return False, f"Command '{cmd_name}' is explicitly blocked."

    # Check against expanded admin whitelist
    if cmd_name not in ADMIN_BINARY_NAMES:
        return False, f"Command '{cmd_name}' is not in the admin allowed list."

    # Apply standard banned flag combinations (same as execute_command)
    args_str = " ".join(args)
    for banned_cmd, banned_flag in BANNED_FLAG_COMBOS:
        if cmd_name == banned_cmd and banned_flag in args_str:
            return False, f"Flag '{banned_flag}' is not permitted with '{banned_cmd}'."

    # Guard against write-mode arguments on admin-only commands
    if cmd_name in ADMIN_WRITE_ARG_PATTERNS:
        banned_args = ADMIN_WRITE_ARG_PATTERNS[cmd_name]
        for arg in args:
            if arg in banned_args:
                return False, (f"'{cmd_name} {arg}' is a write operation. Admin tool is read-only.")

    # Guard ps against process-modifying flags
    if cmd_name == "ps":
        for arg in args:
            if arg in PS_WRITE_FLAGS:
                return False, (f"ps flag '{arg}' modifies process state. Admin tool is read-only.")

    return True, "OK"


def register_library_tools(mcp, safe_dir: str = None):
    """
    Register all library tools with the MCP server (library + CLI tools merged).

    Args:
        mcp: FastMCP server instance
        safe_dir: Ignored (kept for backward compatibility). CLI tools
                  now validate paths dynamically against library roots.

    Tools are conditionally registered based on server mode (LibraryManager,
    LibraryUser, Admin) as defined in server_mode.py.
    """
    from ..config.server_mode import get_tools_for_mode
    from ..config import server_mode
    from ..config.settings import settings

    # CLI tools now validate against registered library roots dynamically.
    # No single SAFE_WORKING_DIR needed.
    # LIBRARIAN_HOME is used only by write_document.

    enabled_tools = get_tools_for_mode(os.getenv("LIBRARIAN_SERVER_MODE", "Admin"))

    def conditional_tool(tool_name):
        """Decorator to conditionally register tools based on server mode."""

        def decorator(func):
            if tool_name in enabled_tools:
                return mcp.tool(tool_name)(func)
            return func

        return decorator

    # Also use conditional_tool for CLI tools (unified namespace)
    def conditional_cli_tool(tool_name):
        """Alias for conditional_tool - CLI tools now use same decorator."""
        return conditional_tool(tool_name)

    # ============================================================================
    # SEARCH TOOLS (Available in all modes)
    # ============================================================================

    @conditional_tool("search_library")
    def search_library(query: str, library: str, limit: int = 10) -> str:
        """
        Search within a specific library using semantic similarity.

        Finds documents similar to the query using vector embeddings.
        Use this for conceptual searches, finding related topics, or
        discovering documents by meaning rather than exact keywords.

        Args:
            query: Search query (describes what you're looking for)
            library: Library name to search (e.g., "botany")
            limit: Maximum results to return (default: 10)

        Returns:
            Formatted search results with relevance scores

        Examples:
            search_library(query="plant taxonomy", library="botany", limit=10)
            search_library(query="invasive species management", library="botany")

        Note: This uses semantic search (vector similarity), not keyword matching.
        For exact keyword searches, use search_library_keyword().
        """
        try:
            library_manager = get_library_manager()

            # Check if library is broken
            if library_manager.is_library_broken(library):
                broken_path = library_manager.get_broken_libraries()[library]
                return f"❌ Library '{library}' has a broken path: {broken_path}\\n\\nThis library cannot be searched. Please fix the path in global_control/.library_control/libraries.yaml or delete the library using delete_library()."

            # Check if library exists
            if not library_manager.get_library(library):
                return f"❌ Library not found: {library}\\n\\nUse list_libraries() to see available libraries."

            orchestrator = get_chromadb_orchestrator()

            # Search library
            results = orchestrator.search_library(library, query, limit)

            if not results:
                return f"🔍 No results found for query: '{query}'\\nLibrary: {library}"

            # Format results
            response = f"🔍 **Semantic Search Results**\\n\\n"
            response += f"**Query:** '{query}'\\n"
            response += f"**Library:** {library}\\n"
            response += f"**Found:** {len(results)} results\\n\\n"

            for i, result in enumerate(results, 1):
                score = result.get("score", 0)
                content = result.get("content") or ""
                metadata = result.get("metadata") or {}

                # Get document info
                doc_name = metadata.get("document_id", "unknown")
                chunk_index = metadata.get("chunk_index", 0)
                total_chunks = metadata.get("total_chunks", 0)

                response += f"**[{i}]** Score: {score:.3f} | {doc_name} (chunk {chunk_index + 1}/{total_chunks})\\n\\n"

                # Show snippet (first 300 chars)
                snippet = content[:300]
                if len(content) > 300:
                    snippet += "..."
                response += f"{snippet}\\n\\n"

            response += f"---\\nLibrary: {library}"
            return response

        except ValueError as e:
            return f"❌ Error: {e}"
        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    @conditional_tool("search_library_keyword")
    def search_library_keyword(
        keyword: str,
        library: str,
        case_sensitive: bool = False,
        limit: int = None,
    ) -> str:
        """
        Search library for exact keyword matches (not semantic similarity).

        Finds ALL chunks containing the keyword, regardless of semantic context.
        Use this when you need to find every occurrence of a specific term.

        Args:
            keyword: Exact word or phrase to search for
            library: Library name to search
            case_sensitive: Match case exactly? (default: False)
            limit: Maximum results to return (None = all matches)

        Returns:
            Formatted results with match counts

        Examples:
            search_library_keyword(keyword="Garry oak", library="botany")
            search_library_keyword(keyword="ecosystem", library="botany", case_sensitive=True)
        """
        try:
            orchestrator = get_chromadb_orchestrator()

            # Get all chunks for library
            all_chunks = orchestrator.get_library_chunks(library_name=library)

            if not all_chunks:
                return f"🔍 No chunks found for library: '{library}'"

            # Filter by keyword
            matching_chunks = keyword_search(
                chunks=all_chunks, keyword=keyword, case_sensitive=case_sensitive
            )

            # Apply limit if specified
            if limit and len(matching_chunks) > limit:
                matching_chunks = matching_chunks[:limit]

            # Format results
            num_chunks = len(matching_chunks)
            total_matches = sum(c.get("match_count", 0) for c in matching_chunks)

            response = f"🔍 **Keyword Search Results**\\n\\n"
            response += f"**Keyword:** '{keyword}'\\n"
            response += f"**Library:** {library}\\n"
            response += f"**Case sensitive:** {case_sensitive}\\n\\n"
            response += f"**Found:** {num_chunks} chunks\\n"
            response += f"**Total occurrences:** {total_matches}\\n\\n"

            # Show all results (or first 50 if very large)
            display_chunks = matching_chunks[:50]

            for i, chunk in enumerate(display_chunks, 1):
                doc_name = (chunk.get("metadata") or {}).get("document_id", "unknown")
                match_count = chunk.get("match_count", 0)
                text = chunk.get("text", "")

                # Create snippet around first match
                search_keyword = keyword if case_sensitive else keyword.lower()
                search_text = text if case_sensitive else text.lower()

                first_match_pos = search_text.find(search_keyword)
                if first_match_pos != -1:
                    start = max(0, first_match_pos - 40)
                    end = min(len(text), first_match_pos + 80)
                    snippet = "..." + text[start:end] + "..."
                else:
                    snippet = text[:100] + "..."

                response += f"**[{i}]** {doc_name} ({match_count} matches)\\n"
                response += f"{snippet}\\n\\n"

            if num_chunks > 50:
                response += f"... and {num_chunks - 50} more results\\n\\n"

            response += f"---\\nLibrary: {library}"
            return response

        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    @conditional_tool("search_across_libraries")
    def search_across_libraries(query: str, limit: int = 10) -> str:
        """
        Search across all libraries using semantic similarity.

        Finds documents similar to the query across all configured libraries.
        Results are ranked by relevance score.

        Args:
            query: Search query (describes what you're looking for)
            limit: Maximum results to return (default: 10)

        Returns:
            Formatted search results with library labels

        Examples:
            search_across_libraries(query="database indexing", limit=10)
            search_across_libraries(query="machine learning algorithms")
        """
        try:
            orchestrator = get_chromadb_orchestrator()

            # Search all libraries
            results = orchestrator.search_all_libraries(query, limit)

            if not results:
                return f"🔍 No results found for query: '{query}'"

            # Format results
            response = f"🔍 **Cross-Library Search Results**\\n\\n"
            response += f"**Query:** '{query}'\\n"
            response += f"**Found:** {len(results)} results\\n\\n"

            for i, result in enumerate(results, 1):
                score = result.get("score", 0)
                content = result.get("content") or ""
                metadata = result.get("metadata") or {}
                library = result.get("library", "unknown")

                # Get document info
                doc_name = metadata.get("document_id", "unknown")

                response += f"**[{i}]** Score: {score:.3f} | [{library}] {doc_name}\\n\\n"

                # Show snippet (first 200 chars)
                snippet = content[:200]
                if len(content) > 200:
                    snippet += "..."
                response += f"{snippet}\\n\\n"

            response += f"---\\nSearched all libraries"
            return response

        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    # ============================================================================
    # LIBRARY MANAGEMENT TOOLS (LibraryManager and Admin modes only)
    # ============================================================================

    @conditional_tool("add_library")
    def add_library(source_path: str, library_name: str, description: str = "") -> str:
        """
        Add a new library and index it immediately (async operation).

        Creates a new library with in-place indexing structure (.librarian/ directory)
        and indexes all documents. This is a long-running operation that runs
        in the background using sync_worker.py to prevent blocking.

        Args:
            source_path: Path to directory containing documents to index
            library_name: Name for the library (e.g., "botany")
            description: Optional description of the library

        Returns:
            Status message indicating library was created and indexing started

        Examples:
            add_library(source_path="/home/peter/botany", library_name="botany")
            add_library(source_path="/home/peter/docs", library_name="documentation", description="Technical docs")

        Note: This spawns a background process for indexing. Monitor progress by checking
        .librarian/sync_progress.json for updates.
        """
        try:
            import subprocess

            library_manager = get_library_manager()

            # Reject relative paths — they resolve against the server's CWD,
            # not the user's shell, which creates .librarian/ in the wrong place
            if not os.path.isabs(source_path):
                return f"❌ Relative path not allowed: '{source_path}'\n\nUse an absolute path like '/Users/yourname/Documents/my-library' or '/home/yourname/my-library'"

            source_path_resolved = Path(source_path).resolve()

            # Validate source path exists
            if not source_path_resolved.exists():
                return f"❌ Source path does not exist: {source_path}"

            # Check if library already exists
            if library_manager.get_library(library_name):
                return f"❌ Library already exists: {library_name}"

            # Register library (creates .librarian/ structure)
            config = library_manager.register_library(
                source_path=source_path_resolved, library_name=library_name, description=description
            )

            # Set active flag
            status = LibraryStatus(source_path_resolved)
            status.set_active(True)

            try:
                # Get sync worker script path
                worker_script = Path(__file__).parent.parent.parent / "scripts" / "sync_worker.py"

                # Spawn sync worker process for initial indexing
                # NOTE: Use subprocess.DEVNULL, not subprocess.PIPE.
                # PIPE creates a buffer nobody reads — once it fills (64KB on
                # Linux), the worker blocks on print()/logging and deadlocks.
                # The worker already logs to .librarian/sync_worker.log.
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(worker_script),
                        "--library",
                        library_name,
                        "--operation",
                        "sync",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )

                # Don't wait for completion - return immediately
                response = f"✅ **Library Created Successfully**\\n\\n"
                response += f"**Name:** {library_name}\\n"
                response += f"**Path:** {source_path_resolved}\\n"
                response += f"**Description:** {description or 'No description'}\\n\\n"
                response += f"**Status:** Indexing in background...\\n\\n"
                response += f"**Structure Created:**\\n"
                response += f"  - {source_path_resolved}/.librarian/chromadb/\\n"
                response += f"  - {source_path_resolved}/.librarian/metadata/\\n"
                response += f"  - {source_path_resolved}/.librarian/status/\\n"
                response += f"**Indexing Progress:**\\n"
                response += f"  - Check .librarian/sync_progress.json for updates\\n"
                response += f"  - Results will be saved to .librarian/sync_results.json\\n\\n"
                response += f"**Next Steps:**\\n"
                response += (
                    f"  - Use search_library() to search the library (after indexing completes)\\n"
                )
                response += f"  - Use sync_library_async() for incremental updates"

                return response

            except Exception as e:
                # Clear active status on error
                status.set_active(False)
                raise e

        except FileExistsError as e:
            return f"❌ {e}"
        except ValueError as e:
            return f"❌ {e}"
        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    @conditional_tool("delete_library")
    def delete_library(library: str, force: bool = False) -> str:
        """
        Delete a library and all its indexed data.

        Removes the library from the registry and deletes the .librarian/ directory
        containing ChromaDB, metadata, and status files. Source documents are NOT deleted.

        Args:
            library: Library name to delete
            force: Skip confirmation (default: False)

        Returns:
            Status message

        WARNING: This operation cannot be undone. All indexed data, metadata,
        and ChromaDB instance will be deleted. Source documents remain untouched.

        Examples:
            delete_library(library="botany")
            delete_library(library="old-library", force=True)
        """
        try:
            library_manager = get_library_manager()

            # Check if library exists (allow broken libraries to be deleted)
            library_info = library_manager.get_library(library, allow_broken=True)
            if not library_info:
                return f"❌ Library not found: {library}\\n\\nUse list_libraries() to see available libraries."

            # Get library info before deletion
            library_path = library_info["path"]

            # Check if library is broken (for custom message)
            is_broken = library_manager.is_library_broken(library)

            # Delete library from registry
            library_manager.unregister_library(library)

            if is_broken:
                # Library was broken, so .librarian/ doesn't exist
                response = f"✅ **Broken Library Removed**\\n\\n"
                response += f"**Name:** {library}\\n"
                response += f"**Path:** {library_path} (path does not exist)\\n\\n"
                response += f"**Action:** Removed from registry\\n"
                response += (
                    f"**Note:** Library path was broken, so no .librarian/ directory was deleted"
                )
            else:
                # Library was valid, delete .librarian/ directory
                librarian_dir = Path(library_path) / ".librarian"
                try:
                    if librarian_dir.exists():
                        import shutil

                        shutil.rmtree(librarian_dir)
                except Exception as e:
                    return f"⚠️ Library removed from registry, but could not delete .librarian/ directory: {e}"

                response = f"✅ **Library Deleted Successfully**\\n\\n"
                response += f"**Name:** {library}\\n"
                response += f"**Path:** {library_path}\\n\\n"
                response += f"**Deleted:**\\n"
                response += f"  - {library_path}/.librarian/ (complete directory)\\n"
                response += f"  - ChromaDB instance\\n"
                response += f"  - Metadata files\\n"
                response += f"  - Status files\\n"
                response += f"**Preserved:**\\n"
                response += f"  - Source documents in {library_path}/"

            return response

        except ValueError as e:
            return f"❌ {e}"
        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    @conditional_tool("list_libraries")
    def list_libraries() -> str:
        """
        List all registered libraries.

        Returns:
            List of all libraries with their configurations

        Examples:
            list_libraries()
        """
        try:
            library_manager = get_library_manager()
            libraries = library_manager.list_libraries()
            broken_libraries = library_manager.get_broken_libraries()

            if not libraries:
                return "📚 No libraries registered.\\n\\nUse add_library() to create a library."

            valid_count = len(libraries) - len(broken_libraries)
            broken_count = len(broken_libraries)

            response = f"📚 **Registered Libraries** ({len(libraries)})"
            if broken_count > 0:
                response += f" — {valid_count} valid, {broken_count} broken"
            response += "\\n\\n"

            for i, lib in enumerate(libraries, 1):
                name = lib.get("name", "unknown")
                path = lib.get("path", "unknown")
                description = lib.get("description", "")
                registered_at = lib.get("registered_at", "unknown")

                if name in broken_libraries:
                    response += f"**[{i}]** ⚠️ {name} (BROKEN)\\n"
                    response += f"  Path: {path}\\n"
                    response += f"  Status: Library path does not exist\\n"
                    if description:
                        response += f"  Description: {description}\\n"
                    response += f"  Registered: {registered_at}\\n\\n"
                else:
                    response += f"**[{i}]** {name}\\n"
                    response += f"  Path: {path}\\n"
                    if description:
                        response += f"  Description: {description}\\n"
                    response += f"  Registered: {registered_at}\\n\\n"

            return response.strip()

        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    @conditional_tool("get_library_stats")
    def get_library_stats(library: str) -> str:
        """
        Get statistics for a specific library.

        Args:
            library: Library name

        Returns:
            Library statistics including document count, chunk count, etc.

        Examples:
            get_library_stats(library="botany")
        """
        try:
            library_manager = get_library_manager()

            # Check if library is broken
            if library_manager.is_library_broken(library):
                broken_path = library_manager.get_broken_libraries()[library]
                return f"❌ Library '{library}' has a broken path: {broken_path}\\n\\nStatistics are not available for broken libraries. Please fix the path in global_control/.library_control/libraries.yaml or delete the library using delete_library()."

            # Check if library exists
            library_info = library_manager.get_library(library)
            if not library_info:
                return f"❌ Library not found: {library}\\n\\nUse list_libraries() to see available libraries."

            # Get library config
            config = library_manager.get_library_config(library)
            if not config:
                return f"❌ Library configuration not found: {library}\\n\\nThe library exists but has no configuration file (.librarian/config.yaml). This may indicate a corrupted library."

            # Extract status information
            status = config.get("status", {})
            library_info = config.get("library", {})
            chromadb_info = config.get("chromadb", {})

            response = f"📊 **Library Statistics**\\n\\n"
            response += f"**Name:** {library}\\n"
            response += f"**Description:** {library_info.get('description', 'No description')}\\n"
            response += f"**Path:** {library_info.get('path', 'unknown')}\\n"
            response += f"**Created:** {library_info.get('created_at', 'unknown')}\\n\\n"

            response += f"**Status:**\\n"
            response += f"  - Active: {status.get('active', False)}\\n"
            response += f"  - Documents: {status.get('document_count', 0)}\\n"
            response += f"  - Chunks: {status.get('chunk_count', 0)}\\n"
            response += f"  - Last Sync: {status.get('last_sync', 'Never')}\\n"
            response += f"  - Last Reindex: {status.get('last_reindex', 'Never')}\\n\\n"

            response += f"**ChromaDB:**\\n"
            response += f"  - Collection: {chromadb_info.get('collection_name', library)}\\n"
            response += f"  - Path: {chromadb_info.get('path', '.librarian/chromadb')}\\n"
            response += f"  - Embedding Model: {chromadb_info.get('embedding_model', 'unknown')}"

            return response

        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    @conditional_tool("sync_library_async")
    def sync_library_async(library: str) -> str:
        """
        Sync library (incremental index of changed files only).

        Performs incremental indexing by comparing SHA-256 checksums and
        only processing changed files. Much faster than rebuild (96% reduction
        in processing for typical updates).

        This operation runs in the background using sync_worker.py to prevent
        blocking the MCP server.

        Args:
            library: Library name to sync

        Returns:
            Status message indicating worker was started

        Examples:
            sync_library_async(library="botany")

        Note: This spawns a background process. Monitor progress by checking
        .librarian/sync_progress.json for updates.
        """
        try:
            import subprocess
            from pathlib import Path

            library_manager = get_library_manager()

            # Check if library is broken
            if library_manager.is_library_broken(library):
                broken_path = library_manager.get_broken_libraries()[library]
                return f"❌ Library '{library}' has a broken path: {broken_path}\\n\\nThis library cannot be synced. Please fix the path in global_control/.library_control/libraries.yaml or delete the library using delete_library()."

            # Check if library exists
            if not library_manager.get_library(library):
                return f"❌ Library not found: {library}\\n\\nUse list_libraries() to see available libraries."

            # Check if library is currently syncing
            library_info = library_manager.get_library(library)
            status = LibraryStatus(Path(library_info["path"]))

            if status.is_active():
                return f"❌ Library is currently syncing: {library}\\n\\nPlease wait for the current operation to complete."

            # Set active flag
            status.set_active(True)

            try:
                # Get sync worker script path
                worker_script = Path(__file__).parent.parent.parent / "scripts" / "sync_worker.py"

                # Spawn sync worker process
                # NOTE: DEVNULL prevents pipe-buffer deadlock (see add_library)
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(worker_script),
                        "--library",
                        library,
                        "--operation",
                        "sync",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )

                # Don't wait for completion - return immediately
                response = f"🚀 **Library Sync Started**\\n\\n"
                response += f"**Library:** {library}\\n\\n"
                response += f"**Operation:** Incremental sync (changed files only)\\n\\n"
                response += f"**Status:** Running in background\\n\\n"
                response += f"**Progress:** Check .librarian/sync_progress.json for updates\\n\\n"
                response += (
                    f"**Results:** Will be saved to .librarian/sync_results.json when complete"
                )

                return response

            except Exception as e:
                # Clear active status on error
                status.set_active(False)
                raise e

        except ValueError as e:
            return f"❌ {e}"
        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    @conditional_tool("rebuild_library_async")
    def rebuild_library_async(library: str) -> str:
        """
        Rebuild library index (clear ChromaDB and re-index all files).

        Performs a complete rebuild of the library index. Use this when:
        - Metadata is corrupted
        - ChromaDB is corrupted
        - Chunking/embedding model has changed
        - Complete rebuild is needed

        This operation runs in the background using sync_worker.py to prevent
        blocking the MCP server.

        Args:
            library: Library name to rebuild

        Returns:
            Status message indicating worker was started

        Examples:
            rebuild_library_async(library="botany")

        Note: This spawns a background process. Monitor progress by checking
        .librarian/sync_progress.json for updates. This is a long-running
        operation (20-30 minutes for full library).
        """
        try:
            library_manager = get_library_manager()
            # backend variable removed - worker creates its own backend

            # Check if library exists
            if not library_manager.get_library(library):
                return f"❌ Library not found: {library}"

            # Check if library is currently syncing
            library_info = library_manager.get_library(library)
            status = LibraryStatus(Path(library_info["path"]))

            if status.is_active():
                return f"❌ Library is currently syncing: {library}\\n\\nPlease wait for the current operation to complete."

            # Set active flag
            status.set_active(True)

            try:
                import subprocess

                # Get sync worker script path
                worker_script = Path(__file__).parent.parent.parent / "scripts" / "sync_worker.py"

                # Spawn rebuild worker process
                # NOTE: DEVNULL prevents pipe-buffer deadlock (see add_library)
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(worker_script),
                        "--library",
                        library,
                        "--operation",
                        "rebuild",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )

                # Don't wait for completion - return immediately
                response = f"🚀 **Library Rebuild Started**\\n\\n"
                response += f"**Library:** {library}\\n\\n"
                response += (
                    f"**Operation:** Full rebuild (clear ChromaDB, re-index all files)\\n\\n"
                )
                response += f"**Status:** Running in background\\n\\n"
                response += f"**Warning:** This is a long-running operation (20-30 minutes for full library)\\n\\n"
                response += f"**Progress:** Check .librarian/sync_progress.json for updates\\n\\n"
                response += (
                    f"**Results:** Will be saved to .librarian/sync_results.json when complete"
                )

                return response

            except Exception as e:
                # Clear active status on error
                status.set_active(False)
                raise e

        except ValueError as e:
            return f"❌ {e}"
        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    # ============================================================================
    # QUERY TOOLS (Available in all modes)
    # ============================================================================

    @conditional_tool("list_library_documents")
    def list_library_documents(library: str, limit: int = 50) -> str:
        """
        List documents in a library.

        Args:
            library: Library name
            limit: Maximum documents to list (default: 50)

        Returns:
            List of documents with metadata

        Examples:
            list_library_documents(library="botany")
            list_library_documents(library="botany", limit=100)
        """
        try:
            library_manager = get_library_manager()

            # Get library info
            library_info = library_manager.get_library(library)
            if not library_info:
                return f"❌ Library not found: {library}"

            library_path = Path(library_info["path"])

            # Load metadata
            import json

            metadata_path = library_path / ".librarian" / "metadata" / "index.json"

            if not metadata_path.exists():
                return f"📄 No documents indexed in library: {library}\\n\\nUse sync_library_async() to index documents."

            with open(metadata_path, "r") as f:
                metadata = json.load(f)

            # Get documents (up to limit)
            documents = list(metadata.items())[:limit]

            response = f"📄 **Documents in '{library}'** ({len(metadata)} total)\\n\\n"

            for doc_path, doc_info in documents:
                indexed_at = doc_info.get("indexed_at", "unknown")
                chunk_count = doc_info.get("chunk_count", 0)
                file_type = doc_info.get("file_type", "unknown")

                response += f"**{doc_path}\\n"
                response += f"  - Type: {file_type}\\n"
                response += f"  - Chunks: {chunk_count}\\n"
                response += f"  - Indexed: {indexed_at}\\n\\n"

            if len(metadata) > limit:
                response += f"... and {len(metadata) - limit} more documents\\n\\n"

            response += f"---\\nLibrary: {library}"
            return response

        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    @conditional_tool("read_library_document")
    def read_library_document(path: str, library: str, max_chars: int = 8000) -> str:
        """
        Read a document from the library (in-place, not shadow).

        Args:
            path: Relative path to document within library
            library: Library name
            max_chars: Maximum characters to return (default: 8000)

        Returns:
            Document content

        Examples:
            read_library_document(path="plants/oak.md", library="botany")
            read_library_document(path="reference/Guide.md", library="botany", max_chars=5000)
        """
        try:
            library_manager = get_library_manager()

            # Get library info
            library_info = library_manager.get_library(library)
            if not library_info:
                return f"❌ Library not found: {library}"

            library_path = Path(library_info["path"])

            # Build document path
            doc_path = library_path / path

            # Security check: ensure path is within library
            try:
                doc_path.resolve().relative_to(library_path.resolve())
            except ValueError:
                return f"❌ Security error: Path '{path}' is outside library '{library}'"

            # Check if file exists
            if not doc_path.exists():
                return f"❌ File not found: {path}\\n\\nLibrary path: {library_path}"

            # Read file
            content = doc_path.read_text(encoding="utf-8")

            # Truncate if needed
            if len(content) > max_chars:
                content = content[:max_chars] + f"\\n\\n... (truncated at {max_chars} characters)"

            response = f"📄 **Document: {path}**\\n"
            response += f"**Library:** {library}\\n"
            response += f"**Size:** {len(content)} characters\\n\\n"
            response += content

            return response

        except Exception as e:
            import traceback

            return f"❌ Error: {str(e)}\\n\\n{traceback.format_exc()}"

    # ============================================================================
    # CLI TOOLS (merged from cli_tools.py)
    # ============================================================================

    @conditional_tool("execute_command")
    def execute_command(command: str, args: list[str] = None, cwd: str = None) -> str:
        """
        Execute a whitelisted command safely inside the allowed directory.

        Args:
            command: The binary to execute (e.g. 'ls', 'cat', 'grep')
            args: List of arguments to pass to the command
            cwd: Optional subdirectory to run in (must be inside allowed directory)

        Returns:
            stdout, stderr, return code
        """
        if args is None:
            args = []
        safe, reason = is_safe_command(command, args)
        if not safe:
            return f"[security error]\\n{reason}"

        if not cwd:
            return (
                "[security error]\n"
                "cwd (working directory) is required. Specify a library path, e.g.:\n"
                "  execute_command(command='ls', cwd='/home/peter/botany')"
            )

        safe, resolved_cwd = is_library_path(cwd)
        if not safe:
            return f"[security error]\n{resolved_cwd}"

        full_cmd = [command] + args

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                cwd=resolved_cwd,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                shell=False,
            )

            output_text = ""
            if result.stdout:
                output_text += f"[stdout]\\n{result.stdout}\\n"
            if result.stderr:
                output_text += f"[stderr]\\n{result.stderr}\\n"
            output_text += f"[return code]\\n{result.returncode}\\n"

            return truncate_output(output_text) if output_text.strip() else "[no output]"

        except subprocess.TimeoutExpired:
            return f"[timeout]\\nCommand timed out after {DEFAULT_TIMEOUT_SECONDS} seconds."
        except FileNotFoundError:
            return f"[error]\\nCommand not found: {command}"
        except PermissionError:
            return f"[error]\\nPermission denied for command: {command}"
        except Exception as e:
            return f"[error]\\nExecution failed: {str(e)}"

    @conditional_tool("admin_command")
    def admin_command(command: str, args: list[str] = None, cwd: str = None) -> str:
        """
        Execute an admin command for development and debugging.

        Expanded command whitelist and path scope compared to execute_command.
        Only available in Admin mode. All operations are read-only observation
        — argument guards block write-mode invocations (e.g. pip install).

        Additional commands available (vs execute_command):
        - ps: Process inspection (read-only flags only)
        - pip: Dependency verification (list/show/search only)
        - env: Dump all environment variables
        - printenv: Print specific environment variable
        - which: Locate a command binary

        Path scope: Library roots AND the project source directory.

        Args:
            command: The binary to execute (e.g. 'ps', 'pip', 'which')
            args: List of arguments to pass to the command
            cwd: Working directory (must be within library root or project directory)

        Returns:
            stdout, stderr, return code
        """
        if args is None:
            args = []

        # Validate command against admin whitelist
        safe, reason = is_safe_admin_command(command, args)
        if not safe:
            return f"[admin security error]\\n{reason}"

        # Require cwd
        if not cwd:
            return (
                "[admin security error]\n"
                "cwd (working directory) is required. "
                "Specify a library path or the project directory.\n"
                "  admin_command(command='ps', args=['aux'], cwd='/home/peter/botany')"
            )

        # Validate path against expanded admin scope
        safe, resolved_cwd = is_admin_path(cwd)
        if not safe:
            return f"[admin security error]\n{resolved_cwd}"

        full_cmd = [command] + args

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                cwd=resolved_cwd,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                shell=False,
            )

            output_text = ""
            if result.stdout:
                output_text += f"[stdout]\\n{result.stdout}\\n"
            if result.stderr:
                output_text += f"[stderr]\\n{result.stderr}\\n"
            output_text += f"[return code]\\n{result.returncode}\\n"

            return truncate_output(output_text) if output_text.strip() else "[no output]"

        except subprocess.TimeoutExpired:
            return f"[timeout]\\nCommand timed out after {DEFAULT_TIMEOUT_SECONDS} seconds."
        except FileNotFoundError:
            return f"[error]\\nCommand not found: {command}"
        except PermissionError:
            return f"[error]\\nPermission denied for command: {command}"
        except Exception as e:
            return f"[error]\\nExecution failed: {str(e)}"

    @conditional_tool("read_document")
    def read_document(
        path: str,
        start_line: int = None,
        end_line: int = None,
        head: int = None,
        tail: int = None,
        max_chars: int = None,
    ) -> str:
        """
        Read contents of a document from within the allowed directory.

        Supports reading entire file or specific portions.

        Args:
            path: Path to the document (within allowed directory)
            start_line: Starting line number (1-based, inclusive)
            end_line: Ending line number (1-based, inclusive)
            head: Read first N lines
            tail: Read last N lines
            max_chars: Maximum characters to return (default: 8000)

        Returns:
            Document contents or error message
        """
        safe, resolved = is_library_path(path)
        if not safe:
            return f"[security error]\n{resolved}"

        if not os.path.isfile(resolved):
            return f"[error]\nFile not found: {resolved}"

        ext = Path(resolved).suffix.lower()
        if ext not in DOCUMENT_EXTENSIONS:
            return f"[error]\nUnsupported file type: {ext}. Allowed: {', '.join(sorted(DOCUMENT_EXTENSIONS))}"

        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            # Determine which lines to read
            if head is not None:
                selected_lines = lines[:head]
                range_info = f"(first {head} lines)"
            elif tail is not None:
                selected_lines = lines[-tail:] if tail > 0 else []
                range_info = f"(last {tail} lines)"
            elif start_line is not None or end_line is not None:
                start = start_line if start_line is not None else 1
                end = end_line if end_line is not None else len(lines)
                selected_lines = lines[start - 1 : end]
                range_info = f"(lines {start}-{end})"
            else:
                selected_lines = lines
                range_info = f"(all {len(lines)} lines)"

            contents = "".join(selected_lines)

            limit = max_chars if max_chars is not None else MAX_OUTPUT_CHARS
            if len(contents) > limit:
                contents = contents[:limit] + f"\\n[output truncated — exceeded {limit} chars]"

            return f"[file: {resolved} {range_info}]\\n\\n{contents}"

        except Exception as e:
            return f"[error]\\nCould not read file: {e}"

    @conditional_tool("list_documents")
    def list_documents(path: str = None, extension: str = None, recursive: bool = True) -> str:
        """
        List documents within the allowed directory.

        Args:
            path: Subdirectory to list (default: allowed directory root)
            extension: Filter by extension e.g. '.md', '.py' (default: all supported)
            recursive: Whether to recurse into subdirectories (default: True)

        Returns:
            List of document paths with sizes
        """
        base = path if path else ""
        if not base:
            manager = get_library_manager()
            libs = manager.list_libraries()
            lib_paths = ", ".join(lib["path"] for lib in libs[:5])
            return f"[error]\nPath is required. Registered library roots: {lib_paths}"
        safe, resolved = is_library_path(base)
        if not safe:
            return f"[security error]\n{resolved}"

        if not os.path.isdir(resolved):
            return f"[error]\nDirectory not found: {resolved}"

        extensions = {extension.lower()} if extension else DOCUMENT_EXTENSIONS

        try:
            results = []

            if recursive:
                for root, dirs, files in os.walk(resolved):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for fname in sorted(files):
                        if Path(fname).suffix.lower() in extensions:
                            full_path = os.path.join(root, fname)
                            size = os.path.getsize(full_path)
                            results.append(f"{full_path} ({size} bytes)")
            else:
                for fname in sorted(os.listdir(resolved)):
                    full_path = os.path.join(resolved, fname)
                    if os.path.isfile(full_path) and Path(fname).suffix.lower() in extensions:
                        size = os.path.getsize(full_path)
                        results.append(f"{full_path} ({size} bytes)")

            if not results:
                return f"[no documents found in {resolved}]"

            output = f"[documents in {resolved}]\\n" + "\\n".join(results)
            output += f"\\n\\n[total: {len(results)} documents]"
            return truncate_output(output)

        except Exception as e:
            return f"[error]\\nCould not list directory: {e}"

    @conditional_tool("search_documents")
    def search_documents(
        query: str, path: str = None, extension: str = None, case_sensitive: bool = False
    ) -> str:
        """
        Search for a text string across documents in the allowed directory.

        Args:
            query: Text string to search for
            path: Subdirectory to search (default: root of allowed directory)
            extension: Limit search to file type e.g. '.md' (default: all supported)
            case_sensitive: Whether search is case sensitive (default: False)

        Returns:
            Matching files and lines with line numbers
        """
        base = path if path else ""
        if not base:
            manager = get_library_manager()
            libs = manager.list_libraries()
            lib_paths = ", ".join(lib["path"] for lib in libs[:5])
            return f"[error]\nPath is required. Registered library roots: {lib_paths}"
        safe, resolved = is_library_path(base)
        if not safe:
            return f"[security error]\n{resolved}"

        if not os.path.isdir(resolved):
            return f"[error]\nDirectory not found: {resolved}"

        extensions = {extension.lower()} if extension else DOCUMENT_EXTENSIONS
        results = []
        files_searched = 0
        files_matched = 0

        try:
            for root, dirs, files in os.walk(resolved):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in sorted(files):
                    if Path(fname).suffix.lower() not in extensions:
                        continue
                    full_path = os.path.join(root, fname)
                    files_searched += 1
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()
                        matches = []
                        for i, line in enumerate(lines, 1):
                            haystack = line if case_sensitive else line.lower()
                            needle = query if case_sensitive else query.lower()
                            if needle in haystack:
                                matches.append(f"  line {i}: {line.rstrip()}")
                        if matches:
                            files_matched += 1
                            results.append(f"\\n{full_path}:")
                            results.extend(matches[:10])
                            if len(matches) > 10:
                                results.append(f"  ... and {len(matches) - 10} more matches")
                    except Exception:
                        continue

            if not results:
                return f"[no matches found for '{query}' in {files_searched} files]"

            output = f"[search results for '{query}']\\n" + "\\n".join(results)
            output += (
                f"\\n\\n[searched {files_searched} files, found matches in {files_matched} files]"
            )
            return truncate_output(output)

        except Exception as e:
            return f"[error]\\nSearch failed: {e}"

    @conditional_tool("document_summary")
    def document_summary(path: str) -> str:
        """
        Get a structural summary of a document without reading full contents.

        Args:
            path: Path to the document

        Returns:
            Structural summary with line numbers
        """
        safe, resolved = is_library_path(path)
        if not safe:
            return f"[security error]\n{resolved}"

        if not os.path.isfile(resolved):
            return f"[error]\nFile not found: {resolved}"

        ext = Path(resolved).suffix.lower()

        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            size = os.path.getsize(resolved)
            word_count = sum(len(line.split()) for line in lines)
            output = f"[summary: {resolved}]\\n"
            output += f"Size: {size} bytes | Lines: {len(lines)} | Words: {word_count}\\n\\n"

            if ext == ".md":
                headings = [
                    (i + 1, line.rstrip()) for i, line in enumerate(lines) if line.startswith("#")
                ]
                if headings:
                    output += "[headings]\\n"
                    for lineno, heading in headings[:50]:
                        output += f"  line {lineno}: {heading}\\n"
                else:
                    output += "[no headings found]\\n"

            elif ext in {".py", ".js", ".ts"}:
                definitions = [
                    (i + 1, line.rstrip())
                    for i, line in enumerate(lines)
                    if line.strip().startswith(
                        ("def ", "class ", "function ", "const ", "async def ")
                    )
                ]
                if definitions:
                    output += "[definitions]\\n"
                    for lineno, defn in definitions[:50]:
                        output += f"  line {lineno}: {defn.strip()}\\n"
                else:
                    output += "[no definitions found]\\n"

            else:
                output += "[first 10 lines]\\n"
                for i, line in enumerate(lines[:10], 1):
                    output += f"  {i}: {line.rstrip()}\\n"

            return output

        except Exception as e:
            return f"[error]\\nCould not summarize file: {e}"

    @conditional_tool("write_document")
    def write_document(path: str, content: str, create_dirs: bool = True, library: str = None) -> str:
        """
        Write content to a file in the librarian workspace.

        All writes go to {LIBRARIAN_HOME}/{path} (global sandbox).
        When a library is specified, also writes to the library's delivery/ directory,
        enabling deliverables to sync to remote devices via Syncthing.

        Args:
            path: File path relative to the librarian workspace (simple format only)
            content: File content to write
            create_dirs: Create parent directories if they don't exist (default: True)
            library: Optional library name for per-library delivery

        Returns:
            Success confirmation with file path and size
        """
        # Validate path BEFORE any processing
        if not path:
            return "[error] Path cannot be empty. Please provide a filename like 'report.md'"

        # SECURITY: Early validation
        if path.startswith("/") or path.startswith("\\"):
            return f"[error] Invalid path format. Use relative paths like 'report.md'"

        if ".." in path:
            return f"[error] Path cannot contain '..'. Use simple paths like 'report.md'"

        # SECURITY: Strip leading/trailing slashes and whitespace
        clean_path = path.strip().strip("/").strip("\\")

        # SECURITY: Reject paths starting with dot
        if clean_path.startswith("."):
            return f"[error] Path cannot start with '.'. Use simple filenames like 'report.md'"

        # SECURITY: Reject paths trying to reference project directory
        if "librarian-mcp" in clean_path.lower():
            return f"[error] Path contains invalid references. Use simple paths like 'report.md'"

        # SECURITY: Reject complex paths
        if "//" in path or "/./" in path:
            return f"[error] Path contains invalid sequences. Use simple paths like 'reports/analysis.md'"

        # SECURITY: Limit directory depth
        depth = clean_path.count("/")
        if depth > 3:
            return (
                f"[error] Path too deep (max 3 levels). Use simple paths like 'reports/analysis.md'"
            )

        # Build final path inside LIBRARIAN_HOME
        from ..config.settings import settings

        librarian_home = str(settings.LIBRARIAN_HOME)
        resolved_real = os.path.realpath(os.path.join(librarian_home, clean_path))
        home_real = os.path.realpath(librarian_home)

        # Validate path stays within LIBRARIAN_HOME
        if not resolved_real.startswith(home_real + os.sep) and resolved_real != home_real:
            return "[error] Write path escapes LIBRARIAN_HOME. Use simple paths like 'report.md'"

        # Check file size limit
        if len(content) > MAX_WRITE_FILE_SIZE:
            return f"[error]\\nContent too large: {len(content)} bytes (max: {MAX_WRITE_FILE_SIZE} bytes)"

        # Create parent directories if requested
        file_dir = os.path.dirname(resolved_real)
        if create_dirs and file_dir and not os.path.exists(file_dir):
            try:
                os.makedirs(file_dir, exist_ok=True)
            except Exception as e:
                return f"[error]\\nCould not create directory {file_dir}: {e}"

        # Prevent overwriting critical system files
        critical_patterns = ["password", "secret", "key", "credential", ".env", "config"]
        path_lower = resolved_real.lower()
        for pattern in critical_patterns:
            if pattern in path_lower:
                return f"[security error]\\nCannot write to files containing '{pattern}' in path"

        # Per-library delivery path (if library specified)
        delivery_path = None
        if library:
            library_manager = get_library_manager()
            library_info = library_manager.get_library(library)
            if library_info:
                delivery_dir = Path(library_info["path"]) / "delivery"
                delivery_dir.mkdir(parents=True, exist_ok=True)
                delivery_path = delivery_dir / clean_path
                # Security: ensure delivery path stays within library delivery/
                delivery_real = os.path.realpath(str(delivery_path))
                delivery_dir_real = os.path.realpath(str(delivery_dir))
                if not delivery_real.startswith(delivery_dir_real + os.sep) and delivery_real != delivery_dir_real:
                    delivery_path = None  # Path escaped delivery dir, skip

        try:
            # Write the file to global sandbox
            with open(resolved_real, "w", encoding="utf-8") as f:
                f.write(content)

            # Log the write operation
            log_entry = f"[write] {resolved_real} ({len(content)} bytes)"
            print(f"[librarian-mcp] {log_entry}")

            # Dual delivery: also write to library delivery/ directory
            if delivery_path:
                delivery_file_dir = os.path.dirname(str(delivery_path))
                if create_dirs and delivery_file_dir and not os.path.exists(delivery_file_dir):
                    os.makedirs(delivery_file_dir, exist_ok=True)
                with open(str(delivery_path), "w", encoding="utf-8") as f:
                    f.write(content)
                log_entry = f"[delivery] {delivery_path} ({len(content)} bytes)"
                print(f"[librarian-mcp] {log_entry}")
                return f"[success]\\nWrote {len(content)} bytes to {resolved_real}\\nDelivered to {delivery_path}\\n"

            return f"[success]\\nWrote {len(content)} bytes to {resolved_real}\\n"

        except Exception as e:
            return f"[error]\\nCould not write file: {e}"

    @conditional_tool("server_info")
    def server_info() -> str:
        """
        Returns server configuration, allowed commands, and supported document types.
        """
        from ..config.settings import settings

        return (
            f"**Server Information**\n\n"
            f"**CLI Security Boundary:** Registered library roots (dynamic)\n\n"
            f"**Report Write Location:** {settings.LIBRARIAN_HOME}\n"
            f"  - write_document() → {settings.LIBRARIAN_HOME}/{{path}}\n"
            f"  - Per-library delivery/ directories for distributed library setups\n\n"
            f"**Allowed Commands:**\n"
            f"  - Text Processing: {', '.join(sorted(['awk', 'cat', 'cut', 'grep', 'head', 'sort', 'tail', 'uniq', 'wc']))}\n"
            f"  - Navigation: {', '.join(sorted(['cd', 'ls', 'pwd', 'tree']))}\n"
            f"  - File Operations: {', '.join(sorted(['diff', 'file', 'find', 'mkdir', 'stat']))}\n"
            f"  - System: {', '.join(sorted(['date', 'echo', 'hostname', 'whoami']))}\n\n"
            f"**Supported Document Types:**\n"
            f"  - Markdown: .md, .rst\n"
            f"  - Plain Text: .txt, .html\n"
            f"  - Code: .js, .py, .ts\n"
            f"  - Data: .json, .yaml, .yml, .toml\n\n"
            f"**Operational Limits:**\n"
            f"  - Command Timeout: {DEFAULT_TIMEOUT_SECONDS} seconds\n"
            f"  - Max Output Size: {MAX_OUTPUT_CHARS} characters\n"
            f"  - Max Write Size: {MAX_WRITE_FILE_SIZE} bytes\n\n"
            f"**Architecture:** Blue Sky (in-place indexing, per-library ChromaDB)"
        )
