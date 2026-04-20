# SPDX-License-Identifier: MIT
#
"""
LibraryStatus - Atomic Status Updates for Library State Management

This component manages library status indicators with atomic file operations
to prevent race conditions and ensure consistent state tracking.

Key Design Decisions:
- Atomic status file updates (temp file + rename + fsync)
- No file locking (deferred to future release based on demand)
- Simple YAML flag for active status
- Status files for human readability
- YAML config for machine readability

Usage:
    status = LibraryStatus(Path("/home/peter/botany"))
    status.set_active(True)
    status.update_sync_time()
    is_syncing = status.is_active()
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime


class LibraryStatus:
    """
    Manage library status indicators with atomic updates.

    This class handles status tracking for libraries including:
    - Active state (is library currently being synced?)
    - Last sync time
    - Last reindex time
    - Document count
    - Chunk count

    All status updates use atomic write patterns to prevent corruption
    from concurrent writes or system crashes.

    Attributes:
        library_path: Root path of the library
        status_dir: Path to .librarian/status/ directory
        config_path: Path to .librarian/config.yaml file
    """

    def __init__(self, library_path: Path):
        """
        Initialize LibraryStatus for a library.

        Args:
            library_path: Root path of the library (contains .librarian/)

        The library_path should be the parent of the .librarian/ directory.
        For example, if .librarian/ is at /home/peter/botany/.librarian/,
        then library_path should be /home/peter/botany
        """
        self.library_path = Path(library_path)
        self.status_dir = self.library_path / '.librarian' / 'status'
        self.config_path = self.library_path / '.librarian' / 'config.yaml'

    def update_status(self, status_type: str, message: str):
        """
        Update status file with atomic write.

        Args:
            status_type: Type of status (e.g., 'last_sync', 'last_reindex', 'document_count')
            message: Status message to write

        This method uses atomic write pattern:
        1. Write to temp file
        2. Atomic rename (overwrites target if exists)
        3. Force fsync to ensure data is written to disk

        This prevents corruption from:
        - Concurrent writes
        - System crashes during write
        - Partial writes

        Example:
            status.update_status('last_sync', '2026-04-06T10:30:00Z')
            status.update_status('document_count', '42')
        """
        # Ensure status directory exists
        self.status_dir.mkdir(parents=True, exist_ok=True)

        status_file = self.status_dir / f"{status_type}.txt"

        # Atomic write: temp file + rename
        temp_file = self.status_dir / f"{status_type}.txt.tmp"

        # Write to temp file
        temp_file.write_text(message)

        # Atomic rename (overwrites target if exists)
        temp_file.replace(status_file)

        # Force flush to disk (prevents data loss on crash)
        try:
            with open(status_file, 'r+') as f:
                os.fsync(f.fileno())
        except (OSError, IOError) as e:
            # fsync not critical on all systems, log warning
            print(f"Warning: Could not fsync {status_file}: {e}")

    def get_status(self, status_type: str) -> str:
        """
        Get status value from status file.

        Args:
            status_type: Type of status to retrieve

        Returns:
            Status message string, or empty string if file doesn't exist

        Example:
            last_sync = status.get_status('last_sync')
            # Returns: '2026-04-06T10:30:00Z' or ''
        """
        status_file = self.status_dir / f"{status_type}.txt"

        if status_file.exists():
            try:
                return status_file.read_text().strip()
            except IOError as e:
                print(f"Warning: Could not read status file {status_file}: {e}")
                return ""

        return ""

    def is_active(self) -> bool:
        """
        Check if library is currently active (being synced).

        Returns:
            True if library is currently being synced, False otherwise

        This reads the 'active' flag from the config.yaml file.
        When a library is being synced, the active flag is set to True
        to prevent concurrent sync operations.

        Note: This is a simple flag without locking. In a future release,
        this may be enhanced with proper file locking if needed based on
        real-world usage patterns.
        """
        config = self._load_config()
        return config.get('status', {}).get('active', False)

    def set_active(self, active: bool):
        """
        Set active status in config.yaml.

        Args:
            active: True to mark library as active (syncing), False to mark as inactive

        This updates the active flag in the config.yaml file.
        The active flag prevents concurrent sync operations on the same library.

        Usage pattern:
            try:
                status.set_active(True)
                # Perform sync operation
                sync_library()
            finally:
                status.set_active(False)

        Note: This uses atomic write pattern to prevent corruption.
        """
        config = self._load_config()

        if 'status' not in config:
            config['status'] = {}

        config['status']['active'] = active

        self._save_config(config)

    def update_sync_time(self):
        """
        Update last sync time in both status file and config.yaml.

        This updates:
        1. status/last_sync.txt (human-readable timestamp)
        2. config.yaml status.last_sync (machine-readable)

        Having the timestamp in both places provides:
        - Easy human reading (status file)
        - Machine access (config YAML)
        - Redundancy (if one is corrupted, the other may survive)
        """
        now = datetime.now().isoformat()

        # Update status file
        self.update_status('last_sync', now)

        # Also update in YAML config
        config = self._load_config()
        if 'status' not in config:
            config['status'] = {}
        config['status']['last_sync'] = now
        self._save_config(config)

    def update_reindex_time(self):
        """
        Update last reindex time in both status file and config.yaml.

        This updates:
        1. status/last_reindex.txt (human-readable timestamp)
        2. config.yaml status.last_reindex (machine-readable)

        A reindex is a complete rebuild of the library index,
        as opposed to an incremental sync.
        """
        now = datetime.now().isoformat()

        # Update status file
        self.update_status('last_reindex', now)

        # Also update in YAML config
        config = self._load_config()
        if 'status' not in config:
            config['status'] = {}
        config['status']['last_reindex'] = now
        self._save_config(config)

    def update_document_count(self, count: int):
        """
        Update document count in both status file and config.yaml.

        Args:
            count: Number of documents in library

        This updates:
        1. status/document_count.txt (human-readable)
        2. config.yaml status.document_count (machine-readable)

        The document count reflects the number of source documents
        that have been indexed (not the number of chunks).
        """
        # Update status file
        self.update_status('document_count', str(count))

        # Also update in YAML config
        config = self._load_config()
        if 'status' not in config:
            config['status'] = {}
        config['status']['document_count'] = count
        self._save_config(config)

    def update_chunk_count(self, count: int):
        """
        Update chunk count in both status file and config.yaml.

        Args:
            count: Number of chunks in library

        This updates:
        1. status/chunk_count.txt (human-readable)
        2. config.yaml status.chunk_count (machine-readable)

        The chunk count reflects the total number of chunks
        across all documents in the library.
        """
        # Update status file
        self.update_status('chunk_count', str(count))

        # Also update in YAML config
        config = self._load_config()
        if 'status' not in config:
            config['status'] = {}
        config['status']['chunk_count'] = count
        self._save_config(config)

    def get_all_status(self) -> Dict[str, str]:
        """
        Get all status values from status directory.

        Returns:
            Dictionary mapping status type to value

        This reads all .txt files in the status directory
        and returns their contents as a dictionary.

        Example:
            {
                'last_sync': '2026-04-06T10:30:00Z',
                'last_reindex': '2026-04-06T09:00:00Z',
                'document_count': '42',
                'chunk_count': '1847'
            }
        """
        status = {}

        if not self.status_dir.exists():
            return status

        for status_file in self.status_dir.glob('*.txt'):
            status_type = status_file.stem  # filename without .txt
            try:
                status[status_type] = status_file.read_text().strip()
            except IOError:
                continue

        return status

    def _load_config(self) -> Dict:
        """
        Load library configuration from config.yaml.

        Returns:
            Configuration dictionary, or empty dict if file doesn't exist

        Uses yaml.safe_load for security (prevents code execution).
        """
        if not self.config_path.exists():
            return {}

        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except (yaml.YAMLError, IOError) as e:
            print(f"Warning: Could not load config: {e}")
            return {}

    def _save_config(self, config: Dict):
        """
        Save library configuration to config.yaml.

        Args:
            config: Configuration dictionary to save

        Uses atomic write pattern (temp file + rename) to prevent corruption.
        """
        # Ensure parent directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        temp_path = self.config_path.with_suffix('.yaml.tmp')
        with open(temp_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

        temp_path.replace(self.config_path)

    def get_config(self) -> Dict:
        """
        Get complete library configuration.

        Returns:
            Full configuration dictionary from config.yaml

        This is a convenience method for external access to the
        complete library configuration.
        """
        return self._load_config()

    def update_config(self, config: Dict):
        """
        Update complete library configuration.

        Args:
            config: Configuration dictionary to save

        This is a convenience method for external updates to the
        complete library configuration.

        Uses atomic write pattern for safety.
        """
        self._save_config(config)
