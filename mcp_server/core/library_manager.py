# SPDX-License-Identifier: MIT
#
"""
LibraryManager - Library Discovery and Lifecycle Management

This component manages the discovery, registration, and lifecycle of libraries.
Each library is a directory containing documents to be indexed, with a .librarian/
subdirectory for configuration, metadata, and ChromaDB storage.

Key Design Decisions:
- No shadow mode - libraries are indexed in-place
- Per-library ChromaDB instances in .librarian/chromadb/
- YAML-based configuration for human readability
- Simple YAML registry for library tracking
- No locking (deferred to future release based on demand)

Usage:
    manager = LibraryManager()
    libraries = manager.discover_libraries(Path("/home/peter"))
    config = manager.register_library(Path("/home/peter/botany"), "botany")
"""

from pathlib import Path
from typing import List, Dict, Optional
import yaml
import shutil
import chromadb
from datetime import datetime


class LibraryManager:
    """
    Manage library discovery, registration, and lifecycle.

    A library is a directory containing documents to be indexed, with a
    .librarian/ subdirectory for configuration, metadata, and ChromaDB storage.
    The library structure is created during registration.

    Attributes:
        registry_path: Path to the libraries.yaml registry file
        libraries: List of registered library dictionaries
    """

    def __init__(self, registry_path: Optional[Path] = None):
        """
        Initialize LibraryManager with library registry.

        Args:
            registry_path: Path to libraries.yaml. Defaults to
                          <project>/global_control/.library_control/libraries.yaml

        The registry is a simple YAML file listing all registered libraries
        with their names, paths, and registration timestamps.
        """
        if registry_path is None:
            # Default system-wide registry location
            registry_path = (
                Path(__file__).parent.parent.parent
                / "global_control"
                / ".library_control"
                / "libraries.yaml"
            )

        self.registry_path = registry_path
        self.libraries = self._load_registry()
        self.broken_libraries = self._detect_broken_libraries()

    def _load_registry(self) -> List[Dict]:
        """
        Load library registry from YAML file.

        Returns:
            List of library dictionaries with keys: name, path, registered_at

        Creates registry file and parent directories if they don't exist.
        Returns empty list if registry file doesn't exist yet.
        """
        # Ensure registry directory exists
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.registry_path.exists():
            # Create empty registry if it doesn't exist
            self._save_registry([])
            return []

        try:
            with open(self.registry_path, "r") as f:
                data = yaml.safe_load(f)
                return data.get("libraries", []) if data else []
        except (yaml.YAMLError, IOError) as e:
            # If registry is corrupted, start fresh
            print(f"Warning: Could not load registry ({e}), starting fresh")
            return []

    def _detect_broken_libraries(self) -> Dict[str, str]:
        """
        Detect libraries with broken paths.

        Returns:
            Dictionary mapping library names to their broken paths

        Checks each registered library's path and identifies those
        that don't exist or are not accessible. Logs warnings for
        each broken library.
        """
        broken = {}
        for lib in self.libraries:
            library_path = Path(lib["path"])
            if not library_path.exists():
                broken[lib["name"]] = str(library_path)
                print(f"[LIBRARY] ⚠️ Broken path for '{lib['name']}': {library_path}")
            elif not library_path.is_dir():
                broken[lib["name"]] = str(library_path)
                print(f"[LIBRARY] ⚠️ Path is not a directory for '{lib['name']}': {library_path}")

        if broken:
            print(f"[LIBRARY] Found {len(broken)} broken libraries - these will be disabled")
        return broken

    def _save_registry(self, libraries: List[Dict]):
        """
        Save library registry to YAML file.

        Args:
            libraries: List of library dictionaries to save

        Uses atomic write pattern (temp file + rename) to prevent corruption.
        """
        # Create registry directory if needed
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file, then rename
        temp_path = self.registry_path.with_suffix(".yaml.tmp")
        with open(temp_path, "w") as f:
            yaml.dump({"libraries": libraries}, f, default_flow_style=False)

        # Atomic rename (overwrites existing if present)
        temp_path.replace(self.registry_path)

    def discover_libraries(self, root_path: Path) -> List[Dict]:
        """
        Scan directory tree for all .librarian/ directories.

        Args:
            root_path: Root directory to start scanning from

        Returns:
            List of library dictionaries found in the directory tree.

        This method scans recursively for .librarian/ directories and
        validates each one to ensure it has the required structure.
        Only valid libraries are included in the results.

        Note: This discovers libraries on disk, which may differ from
        the registered libraries in the registry.
        """
        libraries = []

        # Search recursively for .librarian directories
        for librarian_dir in root_path.rglob(".librarian"):
            # Skip if it's a file, not a directory
            if not librarian_dir.is_dir():
                continue

            # Validate library structure
            if self.is_valid_library(librarian_dir):
                library = self._load_library_from_disk(librarian_dir)
                if library:
                    libraries.append(library)

        return libraries

    def is_valid_library(self, librarian_dir: Path) -> bool:
        """
        Check if directory contains a valid library structure.

        Args:
            librarian_dir: Path to .librarian/ directory

        Returns:
            True if all required components exist, False otherwise.

        Required components:
        - config.yaml: Library configuration file
        - chromadb/: ChromaDB storage directory
        - metadata/: Document metadata storage
        - status/: Status indicator files
        """
        required_items = [
            "config.yaml",  # Library configuration
            "chromadb",  # ChromaDB storage
            "metadata",  # Document metadata
            "status",  # Status indicators
        ]

        for item in required_items:
            item_path = librarian_dir / item
            if not item_path.exists():
                return False

        return True

    def _load_library_from_disk(self, librarian_dir: Path) -> Optional[Dict]:
        """
        Load library configuration from disk.

        Args:
            librarian_dir: Path to .librarian/ directory

        Returns:
            Library dictionary with keys from config.yaml, plus path.
            Returns None if config is missing or invalid.

        Reads the library's config.yaml file and extracts library
        name and other metadata. The library path is the parent
        of the .librarian/ directory.
        """
        config_path = librarian_dir / "config.yaml"

        if not config_path.exists():
            return None

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            if not config or "library" not in config:
                return None

            # Extract library info from config
            library_info = config["library"]
            library_path = librarian_dir.parent  # Parent of .librarian/

            return {
                "name": library_info.get("name"),
                "path": str(library_path),
                "description": library_info.get("description", ""),
                "created_at": library_info.get("created_at"),
                "librarian_dir": str(librarian_dir),
            }
        except (yaml.YAMLError, IOError, KeyError):
            return None

    def register_library(self, source_path: Path, library_name: str, description: str = "") -> Dict:
        """
        Register a new library and create its directory structure.

        Args:
            source_path: Path to the library's source directory
            library_name: Name for the library (used in IDs and config)
            description: Optional description of the library

        Returns:
            Dictionary with library configuration

        Raises:
            ValueError: If source_path doesn't exist
            FileExistsError: If library is already registered

        This method:
        1. Validates the source path exists
        2. Creates .librarian/ directory structure
        3. Creates default config.yaml
        4. Initializes ChromaDB instance
        5. Adds library to registry

        The .librarian/ structure includes:
        - chromadb/: Per-library ChromaDB instance
        - metadata/: Document metadata storage
        - status/: Status indicator files

        Note: sync_progress.json, sync_results.json, and sync_worker.log are
        created by the background sync_worker.py process, not by register_library.
        """
        source_path = source_path.resolve()

        # Validate source path exists
        if not source_path.exists():
            raise ValueError(f"Source path does not exist: {source_path}")

        # Check if library already registered
        if self.get_library(library_name):
            raise FileExistsError(f"Library already registered: {library_name}")

        # Create .librarian/ directory structure
        librarian_dir = source_path / ".librarian"
        librarian_dir.mkdir(exist_ok=True)

        # Create subdirectories
        (librarian_dir / "chromadb").mkdir(exist_ok=True)
        (librarian_dir / "metadata").mkdir(exist_ok=True)
        (librarian_dir / "status").mkdir(exist_ok=True)

        # Create delivery directory for MCP output
        # (synced by Syncthing to remote devices in distributed setups)
        (source_path / "delivery").mkdir(exist_ok=True)

        # Create default .librarianignore if one doesn't exist
        # Prevents indexing of Obsidian config, Syncthing state, and .librarian/ internals
        librarianignore_path = source_path / ".librarianignore"
        if not librarianignore_path.exists():
            librarianignore_path.write_text(
                "# Files and directories to exclude from MCP indexing\n"
                ".obsidian/\n"
                ".librarian/\n"
                ".librarianignore\n"
                ".stignore\n"
            )

        # Create default .stignore for Syncthing if one doesn't exist
        # Excludes .librarian/ from syncing to remote devices
        stignore_path = source_path / ".stignore"
        if not stignore_path.exists():
            stignore_path.write_text(
                "# Syncthing exclusions — do not sync server infrastructure\n"
                ".librarian/\n"
            )

        # Create default config.yaml
        config = self._create_default_config(source_path, library_name, description)
        self._write_config(librarian_dir / "config.yaml", config)

        # Initialize ChromaDB (creates collection)
        self._initialize_chromadb(librarian_dir / "chromadb", library_name)

        # Add to registry
        self._add_to_registry(library_name, source_path, description)

        # Reload registry to pick up changes
        self.libraries = self._load_registry()

        return config

    def _create_default_config(
        self, source_path: Path, library_name: str, description: str
    ) -> Dict:
        """
        Create default library configuration.

        Args:
            source_path: Path to library source directory
            library_name: Name of the library
            description: Optional description

        Returns:
            Dictionary with default configuration

        Configuration includes:
        - Library metadata (name, path, creation timestamp)
        - Indexing settings (file types to index)
        - ChromaDB settings (path, collection name, embedding model)
        - Status settings (active flag, timestamps, counters)
        """
        now = datetime.now().isoformat()

        return {
            "library": {
                "name": library_name,
                "path": str(source_path),
                "description": description,
                "created_at": now,
            },
            "indexing": {
                "enabled": True,
                "file_types": [
                    {"pattern": "*.md", "description": "Markdown documents", "action": "index"},
                    {"pattern": "*.txt", "description": "Text files", "action": "index"},
                    {"pattern": "*.py", "description": "Python code", "action": "index"},
                    {"pattern": "*.sh", "description": "Shell scripts", "action": "index"},
                    {"pattern": "*.yaml", "description": "YAML configuration", "action": "index"},
                    {"pattern": "*.yml", "description": "YAML configuration", "action": "index"},
                    {"pattern": "*.html", "description": "HTML documents", "action": "index"},
                ],
                "ignore_file": ".librarianignore",
            },
            "chromadb": {
                "path": ".librarian/chromadb",
                "collection_name": library_name,
                "embedding_model": "BAAI/bge-small-en-v1.5",
            },
            "status": {
                "active": False,
                "last_sync": None,
                "last_reindex": None,
                "document_count": 0,
                "chunk_count": 0,
            },
        }

    def _write_config(self, config_path: Path, config: Dict):
        """
        Write configuration to YAML file.

        Args:
            config_path: Path where config.yaml should be written
            config: Configuration dictionary to write

        Uses atomic write pattern for safety.
        """
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        temp_path = config_path.with_suffix(".yaml.tmp")
        with open(temp_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        temp_path.replace(config_path)

    def _initialize_chromadb(self, chromadb_path: Path, collection_name: str):
        """
        Initialize ChromaDB instance for library.

        Args:
            chromadb_path: Path where ChromaDB data should be stored
            collection_name: Name for the ChromaDB collection

        Creates a new ChromaDB persistent client and collection
        for this library. The collection will store document
        chunks with library name in metadata for future compatibility.

        Note: If chroma.sqlite3 exists but is 0 bytes (corrupted from
        failed initialization), it will be removed before re-initializing.
        """
        # Clean up corrupted ChromaDB database (0-byte files from failed init)
        # Must be done BEFORE PersistentClient instantiation to avoid SQLite errors
        chroma_db_file = chromadb_path / "chroma.sqlite3"
        if chroma_db_file.exists() and chroma_db_file.stat().st_size == 0:
            print(f"[INIT] Removing corrupted ChromaDB database: {chroma_db_file}")
            chroma_db_file.unlink()

        # Ensure ChromaDB directory exists
        chromadb_path.mkdir(parents=True, exist_ok=True)

        # Create persistent client
        client = chromadb.PersistentClient(
            path=str(chromadb_path),
            settings=chromadb.Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # Create or get collection
        # Note: We include library name in metadata for future merge capability
        try:
            client.get_or_create_collection(
                name=collection_name, metadata={"hnsw:space": "cosine", "library": collection_name}
            )
        except Exception as e:
            print(f"Warning: Could not initialize ChromaDB collection: {e}")

    def _add_to_registry(self, library_name: str, source_path: Path, description: str):
        """
        Add library to registry.

        Args:
            library_name: Name of the library
            source_path: Path to library source directory
            description: Optional description
        """
        library_entry = {
            "name": library_name,
            "path": str(source_path),
            "description": description,
            "registered_at": datetime.now().isoformat(),
        }

        # Reload registry to get current state
        current_libraries = self._load_registry()
        current_libraries.append(library_entry)

        # Save updated registry
        self._save_registry(current_libraries)

    def unregister_library(self, library_name: str):
        """
        Unregister a library and delete its .librarian/ directory.

        Args:
            library_name: Name of the library to unregister

        Raises:
            ValueError: If library not found

        This method:
        1. Removes library from registry
        2. Deletes .librarian/ directory and all contents
        3. Does NOT delete source documents (only .librarian/)

        Warning: This deletes all indexed data, metadata, and
        ChromaDB instance. The operation is not reversible.
        """
        # Get library info
        library = self.get_library(library_name)
        if not library:
            raise ValueError(f"Library not found: {library_name}")

        # Remove from registry
        current_libraries = self._load_registry()
        updated_libraries = [lib for lib in current_libraries if lib["name"] != library_name]
        self._save_registry(updated_libraries)

        # Delete .librarian/ directory
        librarian_dir = Path(library["path"]) / ".librarian"
        if librarian_dir.exists():
            shutil.rmtree(librarian_dir)

        # Reload registry
        self.libraries = self._load_registry()

    def get_library(self, library_name: str, allow_broken: bool = False) -> Optional[Dict]:
        """
        Get library by name.

        Args:
            library_name: Name of the library
            allow_broken: If True, return broken libraries; if False, return None for broken libraries

        Returns:
            Library dictionary or None if not found or broken (and allow_broken=False)

        Searches the registry (not disk) for the library.
        Returns the library's registration information including
        name, path, description, and registration timestamp.

        If allow_broken=False (default), broken libraries return None
        to prevent operations on libraries with invalid paths.
        """
        for library in self.libraries:
            if library["name"] == library_name:
                if not allow_broken and library_name in self.broken_libraries:
                    return None
                return library
        return None

    def list_libraries(self) -> List[Dict]:
        """
        List all registered libraries.

        Returns:
            List of library dictionaries from registry

        Returns libraries in the order they were registered.
        Each library includes name, path, description, and
        registration timestamp.
        """
        return self.libraries.copy()

    def get_broken_libraries(self) -> Dict[str, str]:
        """
        Get all libraries with broken paths.

        Returns:
            Dictionary mapping library names to their broken paths
        """
        return self.broken_libraries.copy()

    def is_library_broken(self, library_name: str) -> bool:
        """
        Check if a library has a broken path.

        Args:
            library_name: Name of the library to check

        Returns:
            True if library has a broken path, False otherwise
        """
        return library_name in self.broken_libraries

    def get_library_config(self, library_name: str) -> Optional[Dict]:
        """
        Load full configuration for a library.

        Args:
            library_name: Name of the library

        Returns:
            Full library configuration from config.yaml, or None if not found

        This loads the complete configuration from the library's
        config.yaml file, including indexing settings, ChromaDB
        settings, and status information.
        """
        library = self.get_library(library_name)
        if not library:
            return None

        config_path = Path(library["path"]) / ".librarian" / "config.yaml"
        if not config_path.exists():
            return None

        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except (yaml.YAMLError, IOError):
            return None
