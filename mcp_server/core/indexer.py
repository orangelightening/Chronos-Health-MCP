# SPDX-License-Identifier: MIT
#
"""
Indexer - In-Place Document Indexing with SHA-256 Change Detection

This component handles indexing of documents into per-library ChromaDB instances.
Documents are indexed in-place (no shadow mode), with SHA-256 checksum-based
change detection for efficient incremental updates.

Key Design Decisions:
- In-place indexing (no shadow copies)
- SHA-256 checksums for change detection
- Incremental indexing (only process changed files)
- .librarianignore support (gitignore-style patterns)
- Per-library ChromaDB instances
- Library name in metadata (for future merge capability)

Usage:
    manager = LibraryManager()
    backend = BackendClient()
    indexer = Indexer(manager, backend)
    results = indexer.index_library("botany")
"""

import hashlib
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime
import chromadb
import logging

# Configure logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Enable debug level

# Create console handler with debug level formatting
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')
handler.setFormatter(formatter)

# Add handler to logger if not already added
if not logger.handlers:
    logger.addHandler(handler)

class Indexer:
    """
    Index documents into per-library ChromaDB with incremental updates.

    This class handles the complete indexing workflow:
    1. Discover files in library (respecting .librarianignore)
    2. Calculate SHA-256 checksums for change detection
    3. Process only changed files (incremental indexing)
    4. Chunk and embed documents using backend
    5. Store chunks in per-library ChromaDB
    6. Update metadata and status files

    Attributes:
        library_manager: LibraryManager instance for library access
        backend_client: Backend client for chunking and embedding
    """

    def __init__(self, library_manager, backend_client):
        """
        Initialize Indexer with dependencies.

        Args:
            library_manager: LibraryManager instance for library operations
            backend_client: Backend client (Chonkie/ChromaDB) for chunking/embedding
        """
        self.library_manager = library_manager
        self.backend_client = backend_client

    def index_library(self, library_name: str) -> Dict:
        """
        Incremental index of library (only changed files).

        Args:
            library_name: Name of library to index

        Returns:
            Dictionary with indexing statistics:
            {
                'added': int,      # New documents indexed
                'updated': int,    # Existing documents updated
                'skipped': int,    # Unchanged documents skipped
                'deleted': int,    # Deleted files removed from index
                'errors': int      # Documents that failed to process
            }

        Raises:
            ValueError: If library not found or invalid

        This method performs incremental indexing:
        1. Load existing metadata (with checksums)
        2. Discover files in library
        3. For each file:
           - Calculate current SHA-256 checksum
           - Compare with stored checksum
           - Skip if unchanged
           - Process if changed or new
        4. Detect deleted files (indexed but not on disk)
        5. Remove deleted files from ChromaDB and metadata
        6. Update metadata and status files

        Typical performance: 2-3 minutes for 1-5% file changes
        """
        # Get library configuration
        library = self.library_manager.get_library(library_name)
        if not library:
            raise ValueError(f"Library not found: {library_name}")

        # Load library configuration
        config = self.library_manager.get_library_config(library_name)
        if not config:
            raise ValueError(f"Library configuration not found: {library_name}")

        library_path = Path(library['path'])

        # Discover files to index (respecting .librarianignore)
        files = self._discover_files(library_path, config)

        # Load existing metadata for change detection
        metadata = self._load_metadata(library_path)

        # === NEW LOGGING START ===


        logger.debug(f"File discovery complete: {len(files)} files found for {library_name}")
        if len(files) < 50:
            for f in files:
                logger.debug(f"Discovered: {f.relative_to(library_path)}")
        else:
            for f in files[:3]:
                logger.debug(f"Discovered (first 3): {f.relative_to(library_path)}")

        loaded_keys = set(metadata.keys()) if metadata else set()
        logger.info(f"Loaded {len(loaded_keys)} indexed files from metadata")
        if len(loaded_keys) < 50:
            for key in list(loaded_keys)[:3]:
                logger.debug(f"Metadata key exists: {key}")
        # === NEW LOGGING END ===

        # Process each file
        results = {
            'added': 0,
            'updated': 0,
            'skipped': 0,
            'deleted': 0,
            'errors': 0
        }

        # First pass: Check which files changed (SHA-256 checksum)
        changed_files = []
        for file_path in files:
            try:
                # Calculate SHA-256 checksum
                checksum = self._calculate_checksum(file_path)

                # Create metadata key
                relative_path = file_path.relative_to(library_path)
                metadata_key = f"{relative_path}"

                # Check if file changed
                existing = metadata.get(metadata_key)

                logger.debug(f"[CHECKSUM] File: {metadata_key}")
                
                if existing:
                    logger.debug(f"  Existing checksum stored: {existing.get('checksum', 'MISSING')[:20]}...")
                    logger.debug(f"  Current checksum computed:   {checksum[:20]}...")
                    if existing.get('checksum') == checksum:
                        logger.debug(f"  → SKIPPED (identical checksums)")
                    else:
                        logger.info(f"  → CHANGED/NEW detected (checksum differs!)")
                else:
                    logger.debug(f"  → NEW FILE (not in metadata yet)")

                if existing and existing.get('checksum') == checksum:
                    # File unchanged, skip processing
                    results['skipped'] += 1
                else:
                    # File is new or changed, add to processing list
                    changed_files.append(file_path)
   

            except Exception as e:
                import traceback
                error_msg = f"Error checking {file_path.relative_to(library_path)}: {str(e)}"
                print(error_msg)
                print(f"Traceback: {traceback.format_exc()}")
                results['errors'] += 1

        # === Cleanup Phase ===
        # Single point of control for all chunk deletion.
        # The backend (chonkie_backend.chunk_files) is now a pure insert-only operation.

        # Identify deleted files (indexed but not on disk)
        disk_files = {str(f.relative_to(library_path)) for f in files}
        indexed_files = set(metadata.keys())
        deleted_files = indexed_files - disk_files

        # Identify updated files (changed files that already exist in metadata)
        updated_file_keys = set()
        for f in changed_files:
            rel = str(f.relative_to(library_path))
            if rel in metadata:
                updated_file_keys.add(rel)

        # Open ChromaDB connection once if any cleanup is needed
        if deleted_files or updated_file_keys:
            db_path_config = config.get('chromadb', {}).get('path', '.librarian/chromadb')
            db_path = str(library_path / db_path_config)
            collection_name = config.get('chromadb', {}).get('collection_name', library_name)

            client = chromadb.PersistentClient(
                path=db_path,
                settings=chromadb.Settings(anonymized_telemetry=False, allow_reset=True)
            )
            collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine", "library": library_name}
            )

            # --- Handle files deleted from disk ---
            deleted_count = 0
            for deleted_file in deleted_files:
                try:
                    abs_path = str(library_path / deleted_file)
                    results_data = collection.get(
                        where={"source": abs_path},
                        limit=None
                    )
                    if results_data['ids']:
                        collection.delete(ids=results_data['ids'])
                        logger.info(f"[DELETE] Removed {len(results_data['ids'])} chunks for deleted file: {deleted_file}")
                        deleted_count += 1
                    else:
                        logger.debug(f"[DELETE] No chunks found for deleted file: {deleted_file}")

                    # Remove from metadata
                    del metadata[deleted_file]

                except Exception as e:
                    import traceback
                    logger.error(f"[DELETE] Error removing deleted file {deleted_file}: {e}")
                    print(f"Traceback: {traceback.format_exc()}")
                    results['errors'] += 1

            results['deleted'] = deleted_count
            if deleted_files:
                logger.info(f"[DELETE] Removed {deleted_count} deleted files from index")

            # --- Handle files being updated (old chunk cleanup) ---
            for updated_file in updated_file_keys:
                try:
                    abs_path = str(library_path / updated_file)
                    results_data = collection.get(
                        where={"source": abs_path},
                        limit=None
                    )
                    if results_data['ids']:
                        collection.delete(ids=results_data['ids'])
                        logger.info(f"[UPDATE] Removed {len(results_data['ids'])} old chunks for: {updated_file}")
                    else:
                        logger.debug(f"[UPDATE] No old chunks to remove for: {updated_file}")

                except Exception as e:
                    import traceback
                    logger.error(f"[UPDATE] Error removing old chunks for {updated_file}: {e}")
                    print(f"Traceback: {traceback.format_exc()}")
                    results['errors'] += 1

        # Second pass: Batch process all changed files through backend (model loads once)
        if changed_files:
            try:
                # Convert to strings for backend
                file_paths = [str(f) for f in changed_files]

                # Use backend to process all files at once (model caching)
                chunks = self.backend_client.chunk_files(
                    file_paths=file_paths,
                    source="library",
                    library_name=library_name
                )

                # Build per-file info from returned chunks (BUG-003 fix: extract document_id)
                file_info = {}  # str(file_path) → {chunk_count, document_id}
                for chunk in chunks:
                    fp = chunk['metadata'].get('source', '')
                    if fp and fp not in file_info:
                        file_info[fp] = {
                            'chunk_count': 0,
                            'document_id': chunk['metadata'].get('document_id'),
                        }
                    if fp:
                        file_info[fp]['chunk_count'] += 1

                # Distinguish added vs updated, store document_id in metadata
                added_count = 0
                updated_count = 0
                for file_path in changed_files:
                    relative_path = file_path.relative_to(library_path)
                    metadata_key = f"{relative_path}"
                    was_indexed = metadata_key in metadata  # Check BEFORE overwriting

                    if was_indexed:
                        updated_count += 1
                    else:
                        added_count += 1

                    info = file_info.get(str(file_path), {})
                    metadata[metadata_key] = {
                        'checksum': self._calculate_checksum(file_path),
                        'indexed_at': datetime.now().isoformat(),
                        'chunk_count': info.get('chunk_count', 0),
                        'file_type': file_path.suffix.lstrip('.'),
                        'size': file_path.stat().st_size,
                        'document_id': info.get('document_id'),  # KEY FIX: store document_id
                    }

                results['added'] = added_count
                results['updated'] = updated_count

            except Exception as e:
                import traceback
                print(f"Error batch processing files: {e}")
                traceback.print_exc()
                results['errors'] += len(changed_files)

        # Save updated metadata
        self._save_metadata(library_path, metadata)

        # Update status files
        self._update_status(library_path, results, config)

        return results

    def reindex_library(self, library_name: str) -> Dict:
        """
        Full reindex of library (clear ChromaDB, re-index all files).

        Args:
            library_name: Name of library to reindex

        Returns:
            Dictionary with indexing statistics (same format as index_library)

        Raises:
            ValueError: If library not found or invalid

        This method performs a complete rebuild:
        1. Clear ChromaDB collection
        2. Clear metadata files
        3. Re-index all files from scratch

        Use this when:
        - Metadata is corrupted
        - ChromaDB is corrupted
        - Chunking/embedding model has changed
        - Complete rebuild is needed

        Typical performance: 20-30 minutes for full library
        """
        # Get library configuration
        library = self.library_manager.get_library(library_name)
        if not library:
            raise ValueError(f"Library not found: {library_name}")

        library_path = Path(library['path'])

        # Clear ChromaDB collection
        self._clear_chromadb(library_path, library_name)

        # Clear metadata
        self._clear_metadata(library_path)

        # Perform full index (all files will be treated as new)
        return self.index_library(library_name)


    def _calculate_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA-256 checksum of file.

        Args:
            file_path: Path to file

        Returns:
            Hexadecimal SHA-256 checksum string

        SHA-256 is used instead of MD5 for:
        - Better collision resistance
        - Security considerations
        - Industry best practice

        File is read in 4KB chunks for memory efficiency.
        """
        sha256 = hashlib.sha256()

        with open(file_path, 'rb') as f:
            # Read in 4KB chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)

        return sha256.hexdigest()

    def _discover_files(self, library_path: Path, config: Dict) -> List[Path]:
        """
        Discover files to index in library.

        Args:
            library_path: Root path of library
            config: Library configuration with file type patterns

        Returns:
            List of file paths to index

        This method:
        1. Loads .librarianignore patterns
        2. Scans for files matching configured patterns
        3. Filters out ignored files
        4. Returns list of files to index

        Only text-based files are discovered (no binaries).
        """
        files = []

        # Load ignore patterns from .librarianignore
        ignore_patterns = self._load_ignore_patterns(library_path)

        # Get file type patterns from config
        file_types = config.get('indexing', {}).get('file_types', [])

        # Scan for each file type pattern
        for file_type_config in file_types:
            pattern = file_type_config.get('pattern')
            if not pattern:
                continue

            # Find files matching pattern (recursive)
            for file_path in library_path.rglob(pattern):
                # Skip if not a file
                if not file_path.is_file():
                    continue

                # Skip if should be ignored
                if self._should_ignore(file_path, library_path, ignore_patterns):
                    continue

                files.append(file_path)

        return files

    def _load_ignore_patterns(self, library_path: Path) -> List[str]:
        """
        Load ignore patterns from .librarianignore file.

        Args:
            library_path: Root path of library

        Returns:
            List of ignore pattern strings

        The .librarianignore file uses gitignore-style patterns:
        - Lines starting with # are comments
        - Empty lines are ignored
        - Patterns are simple substring matches (can be enhanced later)

        Common patterns:
        - .git/ - Ignore git directories
        - node_modules/ - Ignore node modules
        - *.tmp - Ignore temp files
        """
        ignore_file = library_path / '.librarianignore'

        if not ignore_file.exists():
            return []

        patterns = []
        try:
            with open(ignore_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue

                    patterns.append(line)
        except IOError as e:
            print(f"Warning: Could not read .librarianignore: {e}")

        return patterns

    def _should_ignore(self, file_path: Path, library_path: Path,
                      ignore_patterns: List[str]) -> bool:
        """
        Check if file should be ignored based on patterns.

        Args:
            file_path: Path to file to check
            library_path: Root path of library
            ignore_patterns: List of ignore patterns

        Returns:
            True if file should be ignored, False otherwise

        This is a simple pattern matching implementation.
        Can be enhanced to support full gitignore semantics
        (wildcards, negation, etc.) in future releases.
        """
        # Always ignore .librarian/ directory itself
        if '.librarian' in file_path.parts:
            return True

        # Check each pattern
        for pattern in ignore_patterns:
            # Simple substring match (can be enhanced later)
            if pattern in str(file_path):
                return True

        return False


    def _load_metadata(self, library_path: Path) -> Dict:
        """
        Load document metadata from library.

        Args:
            library_path: Root path of library

        Returns:
            Dictionary mapping file paths to metadata

        Metadata structure:
        {
            'path/to/file.md': {
                'checksum': 'sha256_hash',
                'indexed_at': '2026-04-06T10:30:00Z',
                'chunk_count': 5,
                'file_type': 'md',
                'size': 2048
            }
        }
        """
        metadata_path = library_path / '.librarian' / 'metadata' / 'index.json'

        if not metadata_path.exists():
            return {}

        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load metadata ({e}), starting fresh")
            return {}

    def _save_metadata(self, library_path: Path, metadata: Dict):
        """
        Save document metadata to library.

        Args:
            library_path: Root path of library
            metadata: Metadata dictionary to save

        Uses atomic write pattern (temp file + rename) to prevent corruption.
        """
        metadata_dir = library_path / '.librarian' / 'metadata'
        metadata_dir.mkdir(parents=True, exist_ok=True)

        metadata_path = metadata_dir / 'index.json'

        # Atomic write
        temp_path = metadata_path.with_suffix('.json.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        temp_path.replace(metadata_path)

    def _clear_chromadb(self, library_path: Path, library_name: str):
        """
        Clear ChromaDB collection for library.

        Args:
            library_path: Root path of library
            library_name: Name of library

        Deletes and recreates the ChromaDB collection,
        effectively removing all indexed data.
        """
        chromadb_path = library_path / '.librarian' / 'chromadb'

        try:
            client = chromadb.PersistentClient(
                path=str(chromadb_path),
                settings=chromadb.Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                )
            )

            collection_name = library_name

            # Delete collection if it exists
            try:
                client.delete_collection(name=collection_name)
            except Exception:
                # Collection might not exist, that's okay
                pass

            # Create new empty collection
            client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine", "library": library_name}
            )
        except Exception as e:
            print(f"Warning: Could not clear ChromaDB: {e}")

    def _clear_metadata(self, library_path: Path):
        """
        Clear metadata files for library.

        Args:
            library_path: Root path of library

        Deletes the metadata/index.json file.
        """
        metadata_path = library_path / '.librarian' / 'metadata' / 'index.json'

        if metadata_path.exists():
            metadata_path.unlink()

    def _update_status(self, library_path: Path, results: Dict, config: Dict):
        """
        Update status files for library.

        Args:
            library_path: Root path of library
            results: Indexing results dictionary
            config: Library configuration

        Updates:
        - status/last_sync.txt
        - status/document_count.txt
        - status/chunk_count.txt
        - config.yaml (status section)
        """
        status_dir = library_path / '.librarian' / 'status'
        status_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()

        # Update last_sync.txt
        (status_dir / 'last_sync.txt').write_text(now)

        # Update document count
        # Count from results (added + updated = documents processed)
        docs_processed = results.get('added', 0) + results.get('updated', 0)

        # Load existing config
        config_path = library_path / '.librarian' / 'config.yaml'
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    full_config = yaml.safe_load(f)

                # Update status section
                if 'status' not in full_config:
                    full_config['status'] = {}

                full_config['status']['last_sync'] = now

                # Update document count if we have metadata
                metadata = self._load_metadata(library_path)
                full_config['status']['document_count'] = len(metadata)

                # Calculate chunk count
                chunk_count = sum(m.get('chunk_count', 0) for m in metadata.values())
                full_config['status']['chunk_count'] = chunk_count

                # Save updated config
                temp_path = config_path.with_suffix('.yaml.tmp')
                with open(temp_path, 'w') as f:
                    yaml.dump(full_config, f, default_flow_style=False)
                temp_path.replace(config_path)

            except (yaml.YAMLError, IOError) as e:
                print(f"Warning: Could not update config: {e}")
