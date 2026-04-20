# SPDX-License-Identifier: MIT

"""
Sync Worker - Background Indexing Process for Blue Sky Architecture

This script runs as a separate spawned process for long-running indexing operations,
allowing the MCP server to remain responsive while libraries are being indexed.

Usage:
    python sync_worker.py --library botany --operation sync
    python sync_worker.py --library botany --operation rebuild

Operations:
    - sync: Incremental sync (only changed files)
    - rebuild: Full rebuild (clear ChromaDB, re-index all files)

This worker is spawned by async tools in library_tools.py and runs independently,
updating library status files to report progress.
"""

import argparse
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_server.core.library_manager import LibraryManager
from mcp_server.core.indexer import Indexer
from mcp_server.core.library_status import LibraryStatus


def setup_logging(library_path: Path):
    """
    Setup logging for the sync worker.

    Args:
        library_path: Path to library (for log file location)

    Returns:
        Configured logger instance

    Logs are written to .librarian/sync_worker.log for debugging and monitoring.
    """
    log_dir = library_path / '.librarian'
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / 'sync_worker.log'

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return logging.getLogger(__name__)


def update_progress(library_path: Path, operation: str, message: str, progress: int = None):
    """
    Update progress information for monitoring.

    Args:
        library_path: Path to library
        operation: Operation type (sync, rebuild)
        message: Progress message
        progress: Optional progress percentage (0-100)

    Progress is written to .librarian/sync_progress.json for external monitoring.
    """
    progress_dir = library_path / '.librarian'
    progress_dir.mkdir(parents=True, exist_ok=True)

    progress_file = progress_dir / 'sync_progress.json'

    progress_data = {
        'operation': operation,
        'message': message,
        'timestamp': datetime.now().isoformat(),
        'progress': progress
    }

    # Atomic write
    temp_file = progress_file.with_suffix('.json.tmp')
    with open(temp_file, 'w') as f:
        json.dump(progress_data, f, indent=2)
    temp_file.replace(progress_file)


def sync_library(library_name: str, library_path: Path, logger) -> dict:
    """
    Perform incremental sync of library.

    Args:
        library_name: Name of library to sync
        library_path: Path to library
        logger: Logger instance

    Returns:
        Dictionary with sync results (added, updated, skipped, errors)

    This performs incremental indexing using SHA-256 checksums to detect
    changed files. Only files with different checksums are re-processed.
    """
    logger.info(f"Starting incremental sync for library: {library_name}")

    try:
        # Initialize components
        manager = LibraryManager()

        # Get library config for per-library database path and collection
        config = manager.get_library_config(library_name)
        if not config:
            raise ValueError(f"Library config not found: {library_name}")

        # Construct absolute database path from library config
        db_path_config = config.get('chromadb', {}).get('path', '.librarian/chromadb')
        db_path = str(library_path / db_path_config)

        # Get collection name from library config
        collection_name = config.get('chromadb', {}).get('collection_name', library_name)

        # Get backend for chunking
        from mcp_server.backend.factory import get_backend as create_backend
        from mcp_server.config.settings import settings

        backend = create_backend(
            backend_type=settings.BACKEND,
            collection_name=collection_name,
            db_path=db_path,
        )

        # Create indexer
        indexer = Indexer(manager, backend)

        # Update progress
        update_progress(library_path, 'sync', 'Starting incremental sync...', 0)

        # Perform incremental sync
        results = indexer.index_library(library_name)

        logger.info(f"Sync complete: {results}")
        update_progress(library_path, 'sync', 'Sync complete!', 100)

        return results

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        update_progress(library_path, 'sync', f'Sync failed: {e}', None)
        raise


def rebuild_library(library_name: str, library_path: Path, logger) -> dict:
    """
    Perform full rebuild of library index.

    Args:
        library_name: Name of library to rebuild
        library_path: Path to library
        logger: Logger instance

    Returns:
        Dictionary with rebuild results (added, updated, skipped, errors)

    This performs a complete rebuild by clearing ChromaDB and re-indexing
    all files from scratch. Use this when metadata is corrupted or the
    chunking/embedding model has changed.
    """
    logger.info(f"Starting full rebuild for library: {library_name}")

    try:
        # Initialize components
        manager = LibraryManager()

        # Get library config for per-library database path and collection
        config = manager.get_library_config(library_name)
        if not config:
            raise ValueError(f"Library config not found: {library_name}")

        # Construct absolute database path from library config
        db_path_config = config.get('chromadb', {}).get('path', '.librarian/chromadb')
        db_path = str(library_path / db_path_config)

        # Get collection name from library config
        collection_name = config.get('chromadb', {}).get('collection_name', library_name)

        # Get backend for chunking
        from mcp_server.backend.factory import get_backend as create_backend
        from mcp_server.config.settings import settings

        backend = create_backend(
            backend_type=settings.BACKEND,
            collection_name=collection_name,
            db_path=db_path,
        )

        # Create indexer
        indexer = Indexer(manager, backend)

        # Update progress
        update_progress(library_path, 'rebuild', 'Starting full rebuild...', 0)

        # Perform full rebuild
        results = indexer.reindex_library(library_name)

        logger.info(f"Rebuild complete: {results}")
        update_progress(library_path, 'rebuild', 'Rebuild complete!', 100)

        return results

    except Exception as e:
        logger.error(f"Rebuild failed: {e}")
        update_progress(library_path, 'rebuild', f'Rebuild failed: {e}', None)
        raise


def main():
    """
    Main entry point for sync worker process.

    Parses command line arguments and executes the requested operation.
    This is designed to be spawned as a subprocess by async tools.
    """
    parser = argparse.ArgumentParser(
        description='Sync Worker - Background library indexing process',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--library',
        required=True,
        help='Library name to process'
    )

    parser.add_argument(
        '--operation',
        required=True,
        choices=['sync', 'rebuild'],
        help='Operation to perform'
    )

    parser.add_argument(
        '--config-dir',
        help='Path to librarian control directory (default: <project>/global_control/.library_control)'
    )

    args = parser.parse_args()

    # Get library information
    manager = LibraryManager()
    library = manager.get_library(args.library)

    if not library:
        print(f"Error: Library not found: {args.library}", file=sys.stderr)
        sys.exit(1)

    library_path = Path(library['path'])

    # Setup logging
    logger = setup_logging(library_path)

    logger.info(f"Sync worker started for library: {args.library}")
    logger.info(f"Operation: {args.operation}")
    logger.info(f"Library path: {library_path}")

    # Set active status
    status = LibraryStatus(library_path)

    try:
        status.set_active(True)
        logger.info("Set library status to active")

        # Execute requested operation
        if args.operation == 'sync':
            results = sync_library(args.library, library_path, logger)
        else:  # rebuild
            results = rebuild_library(args.library, library_path, logger)

        # Log results
        logger.info(f"Operation completed successfully:")
        logger.info(f"  - Added: {results.get('added', 0)}")
        logger.info(f"  - Updated: {results.get('updated', 0)}")
        logger.info(f"  - Skipped: {results.get('skipped', 0)}")
        logger.info(f"  - Errors: {results.get('errors', 0)}")

        # Write final results to file
        results_dir = library_path / '.librarian'
        results_dir.mkdir(parents=True, exist_ok=True)

        results_file = results_dir / 'sync_results.json'
        with open(results_file, 'w') as f:
            json.dump({
                'operation': args.operation,
                'library': args.library,
                'timestamp': datetime.now().isoformat(),
                'results': results,
                'status': 'completed'
            }, f, indent=2)

        logger.info(f"Results saved to: {results_file}")

    except Exception as e:
        logger.error(f"Operation failed: {e}")
        logger.info("Exiting with error code 1")

        # Write error results
        results_dir = library_path / '.librarian'
        results_dir.mkdir(parents=True, exist_ok=True)

        results_file = results_dir / 'sync_results.json'
        with open(results_file, 'w') as f:
            json.dump({
                'operation': args.operation,
                'library': args.library,
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'status': 'failed'
            }, f, indent=2)

        sys.exit(1)

    finally:
        # Clear active status
        try:
            status.set_active(False)
            logger.info("Cleared library active status")
        except Exception as e:
            logger.error(f"Failed to clear active status: {e}")

    logger.info("Sync worker finished")


if __name__ == "__main__":
    main()
