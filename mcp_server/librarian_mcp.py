# SPDX-License-Identifier: MIT
#
#!/usr/bin/env python3

"""
Librarian MCP Server - Unified librarian and CLI access server.

This server provides:
- Library tools: Search, sync, and manage documents in ChromaDB
- CLI tools: Secure command execution and file access

Usage:
    python mcp_server/librarian_mcp.py [options]

Options:
    --documents-dir PATH  Document storage location (default: ./documents)
    --chroma-path PATH    ChromaDB data directory (default: ./chroma_db)
    --metadata-path PATH  Metadata storage directory (default: ./metadata)
"""

import sys
import argparse
from pathlib import Path

try:
    from fastmcp import FastMCP
except ImportError:
    print("Error: fastmcp not installed. Run: pip install fastmcp")
    sys.exit(1)

from mcp_server.tools.library_tools import register_library_tools
# CLI tools now merged into library_tools - single unified namespace
from mcp_server.config.librarian_prompt import get_librarian_instructions


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Librarian MCP Server - Document library and CLI access",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --safe-dir removed: CLI tools now validate against registered library roots

    parser.add_argument(
        "--documents-dir",
        default=None,
        help="Document storage location (default: ./documents)",
    )

    parser.add_argument(
        "--chroma-path",
        default=None,
        help="ChromaDB data directory (default: ./chroma_db)",
    )

    parser.add_argument(
        "--metadata-path",
        default=None,
        help="Metadata storage directory (default: ./metadata)",
    )

    parser.add_argument(
        "--port", type=int, default=8000, help="Port for HTTP transport (default: 8000)"
    )

    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "http"],
        help="Transport protocol: stdio or http (default: stdio)",
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP transport (default: 0.0.0.0)",
    )

    parser.add_argument(
        "--mode",
        default="Admin",
        choices=["Admin", "LibraryManager", "LibraryUser"],
        help="Server mode: Admin (default), LibraryManager, or LibraryUser",
    )

    return parser.parse_args()


def main():
    """Main entry point for the Librarian MCP Server."""
    args = parse_arguments()

    # Update settings from command line arguments or environment variables
    from mcp_server.config import settings
    import os

    # Support environment variables for configuration
    # Environment variables take precedence over defaults for MCP usage
    documents_dir = os.getenv("LIBRARIAN_DOCUMENTS_DIR") or args.documents_dir
    chroma_path = os.getenv("LIBRARIAN_CHROMA_PATH") or args.chroma_path
    metadata_path = os.getenv("LIBRARIAN_METADATA_PATH") or args.metadata_path

    # Transport configuration
    transport = os.getenv("LIBRARIAN_TRANSPORT", args.transport)
    host = os.getenv("LIBRARIAN_HOST", args.host)
    port = int(os.getenv("LIBRARIAN_PORT", str(args.port)))
    server_mode = os.getenv("LIBRARIAN_SERVER_MODE", args.mode)

    # Set server mode environment variable for tool registration
    os.environ["LIBRARIAN_SERVER_MODE"] = server_mode

    # Update settings
    if documents_dir:
        settings.Settings.DOCUMENTS_DIR = documents_dir
        os.environ["LIBRARIAN_DOCUMENTS_DIR"] = documents_dir

    if chroma_path:
        settings.Settings.CHROMA_PATH = chroma_path
        os.environ["LIBRARIAN_CHROMA_PATH"] = chroma_path

    if metadata_path:
        settings.Settings.METADATA_PATH = metadata_path
        os.environ["LIBRARIAN_METADATA_PATH"] = metadata_path

    # Ensure directories exist
    settings.Settings.ensure_directories()

    # Create MCP server with librarian persona
    instructions = get_librarian_instructions(
        safe_dir=str(settings.Settings.LIBRARIAN_HOME),
        documents_dir=settings.Settings.DOCUMENTS_DIR,
        chroma_path=settings.Settings.CHROMA_PATH,
        metadata_path=settings.Settings.METADATA_PATH,
    )

    mcp = FastMCP("librarian-mcp", instructions=instructions)

    # Register all tools (library + CLI merged into single namespace)
    register_library_tools(mcp)

    # Print startup info
    print(f"Librarian MCP Server starting...", file=sys.stderr)
    print(f"  Transport: {transport}", file=sys.stderr)
    print(f"  Server mode: {server_mode}", file=sys.stderr)
    print(f"  Report write dir: {settings.Settings.LIBRARIAN_HOME}", file=sys.stderr)
    print(f"  CLI boundary: registered library roots (dynamic)", file=sys.stderr)
    print(f"  Documents: {settings.Settings.DOCUMENTS_DIR}", file=sys.stderr)
    print(f"  ChromaDB: {settings.Settings.CHROMA_PATH}", file=sys.stderr)
    print(f"  Metadata: {settings.Settings.METADATA_PATH}", file=sys.stderr)

    if transport == "http":
        print(f"  HTTP server: http://{host}:{port}", file=sys.stderr)

    # Run server with appropriate transport
    if transport == "http":
        mcp.run(transport="http", host=host, port=port, stateless_http=True)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
