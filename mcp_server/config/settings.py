# SPDX-License-Identifier: MIT
"""
Configuration settings for Librarian MCP Server.

Blue Sky Architecture:
- Per-library ChromaDB instances (no global database)
- CLI tools validated against registered library roots (no single SAFE_DIR)
- Reports written to central LIBRARIAN_HOME directory
"""
import os
from pathlib import Path
from typing import Literal, Set


class Settings:
    """Configuration settings for the Librarian MCP Server."""

    # Paths
    PROJECT_ROOT = Path(__file__).parent.parent.parent

    # ── Report write location ──────────────────────────────────────
    # All write_document output goes here, regardless of which library
    # the report is about. One central sandboxed directory.
    LIBRARIAN_HOME = Path(
        os.getenv("LIBRARIAN_HOME", str(Path.home() / ".librarian"))
    )

    # ── Library registry ───────────────────────────────────────────
    # CLI tools (execute_command, read_document, etc.) validate paths
    # against registered library roots dynamically. No single SAFE_DIR.
    #
    # The library registry lives at:
    LIBRARY_REGISTRY = Path(
        os.getenv("LIBRARIAN_REGISTRY",
                  str(PROJECT_ROOT / "global_control" / ".library_control" / "libraries.yaml"))
    )

    # ── Document storage (legacy) ──────────────────────────────────
    DOCUMENTS_DIR = os.getenv("LIBRARIAN_DOCUMENTS_DIR",
                              str(PROJECT_ROOT / "documents"))

    # ── Metadata storage ───────────────────────────────────────────
    METADATA_PATH = os.getenv("LIBRARIAN_METADATA_PATH",
                              str(PROJECT_ROOT / "metadata"))

    # ── ChromaDB: per-library instances ─────────────────────────────
    # No global default. Empty strings ensure ChromaBackend fails
    # clearly if called without explicit per-library paths.
    CHROMA_PATH = os.getenv("LIBRARIAN_CHROMA_PATH", "")
    CHROMA_COLLECTION = os.getenv("LIBRARIAN_CHROMA_COLLECTION", "")

    # ── Backend selection ───────────────────────────────────────────
    _backend_env = os.getenv("LIBRARIAN_BACKEND", "chonkie")
    if _backend_env not in ("chroma", "chonkie"):
        raise ValueError(
            f"Invalid LIBRARIAN_BACKEND value: '{_backend_env}'. "
            f"Must be 'chroma' or 'chonkie'."
        )
    BACKEND: Literal["chroma", "chonkie"] = _backend_env  # type: ignore

    # ── Chonkie ────────────────────────────────────────────────────
    CHONKIE_URL = os.getenv("LIBRARIAN_CHONKIE_URL", "http://localhost:8000")

    # ── Document processing ────────────────────────────────────────
    MAX_DOCUMENT_SIZE = int(os.getenv("LIBRARIAN_MAX_DOCUMENT_SIZE", "10000000"))
    CHUNK_SIZE = int(os.getenv("LIBRARIAN_CHUNK_SIZE", "1000"))

    # ── Text-only extensions (no binaries in Blue Sky) ─────────────
    DEFAULT_EXTENSIONS: Set[str] = {
        ".md", ".txt", ".rst", ".log",
        ".sh", ".bash", ".zsh",
        ".py", ".js", ".ts", ".json",
        ".yaml", ".yml", ".toml",
        ".html", ".css", ".scss",
        ".csv", ".tsv",
    }

    # ── Security ───────────────────────────────────────────────────
    MAX_OUTPUT_CHARS = int(os.getenv("LIBRARIAN_MAX_OUTPUT_CHARS", "8000"))
    COMMAND_TIMEOUT = int(os.getenv("LIBRARIAN_COMMAND_TIMEOUT", "15"))

    # Active lock timeout: auto-clear stale active flags (minutes)
    ACTIVE_LOCK_TIMEOUT_MINUTES = int(
        os.getenv("LIBRARIAN_ACTIVE_LOCK_TIMEOUT", "60")
    )

    @classmethod
    def ensure_directories(cls):
        """Ensure required directories exist."""
        cls.LIBRARIAN_HOME.mkdir(parents=True, exist_ok=True)
        Path(cls.DOCUMENTS_DIR).mkdir(parents=True, exist_ok=True)
        Path(cls.METADATA_PATH).mkdir(parents=True, exist_ok=True)
        # No global CHROMA_PATH — each library has its own


# Singleton instance
settings = Settings()

# Ensure directories exist on import
settings.ensure_directories()