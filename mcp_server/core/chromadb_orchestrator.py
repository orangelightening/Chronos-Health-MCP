# SPDX-License-Identifier: MIT
#
"""
ChromaDBOrchestrator - Per-Library ChromaDB Connection Management

This component manages ChromaDB connections for multiple libraries,
with each library having its own ChromaDB instance for isolation
and independent management.

Key Design Decisions:
- Per-library ChromaDB instances (.librarian/chromadb/)
- Simple connection dictionary (no pooling, deferred to 1.1 based on demand)
- Synchronous queries (async parallel search deferred to 1.1 based on demand)
- Library name in metadata (for future merge capability)
- Sequential cross-library search (acceptable for simple systems)

Performance Notes:
- Single library search: ~100ms
- 10 libraries (sequential): ~1000ms (acceptable for simple systems)
- 100 libraries (sequential): ~10000ms (may need async in 1.1)

Memory Usage:
- Each connection: ~50MB
- 10 libraries: ~500MB (acceptable)
- 100 libraries: ~5GB (may need connection cleanup in 1.1)

Usage:
    orchestrator = ChromaDBOrchestrator(library_manager)
    results = orchestrator.search_library("botany", "plant taxonomy", 10)
    all_results = orchestrator.search_all_libraries("semantics", 10)
    chunks = orchestrator.get_library_chunks("botany")  # For keyword search
"""

import chromadb
from pathlib import Path
from typing import List, Dict, Optional


class ChromaDBOrchestrator:
    """
    Manage per-library ChromaDB connections and search operations.

    This class provides a unified interface for searching across multiple
    independent ChromaDB instances, one per library. Each library has its
    own ChromaDB instance at .librarian/chromadb/ for isolation.

    The orchestrator maintains connections in memory and provides methods
    for searching single libraries or across all libraries.

    Attributes:
        library_manager: LibraryManager instance for library access
        connections: Dictionary mapping library names to ChromaDB clients
    """

    def __init__(self, library_manager):
        """
        Initialize ChromaDBOrchestrator with library manager.

        Args:
            library_manager: LibraryManager instance for library operations

        The orchestrator uses the LibraryManager to:
        - Get library paths
        - Access library configurations
        - Validate library existence
        """
        self.library_manager = library_manager
        self.connections = {}  # library_name → chromadb_client

    def get_connection(self, library_name: str):
        """
        Get or create ChromaDB connection for specific library.

        Args:
            library_name: Name of the library

        Returns:
            ChromaDB PersistentClient instance

        Raises:
            ValueError: If library not found

        Connection Management:
        - Creates connection on first use
        - Caches connection in self.connections dictionary
        - Reuses cached connection for subsequent calls
        - No connection pooling (deferred to 1.1 based on demand)
        - No connection cleanup (deferred to 1.1 based on demand)

        Note: Connections persist in memory for the lifetime of the
        orchestrator instance. For heavy users (100+ libraries), this
        may consume significant memory (~5GB). Monitor and add cleanup
        in 1.1 if needed based on real-world usage.
        """
        # Return cached connection if available
        if library_name in self.connections:
            return self.connections[library_name]

        # Get library information
        library = self.library_manager.get_library(library_name)
        if not library:
            raise ValueError(f"Library not found: {library_name}")

        # Build ChromaDB path
        library_path = Path(library['path'])
        chromadb_path = library_path / '.librarian' / 'chromadb'

        # Create persistent client
        # Settings: anonymized_telemetry=False, allow_reset=True
        client = chromadb.PersistentClient(
            path=str(chromadb_path),
            settings=chromadb.Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )

        # Cache connection for reuse
        self.connections[library_name] = client

        return client

    def search_library(self, library_name: str, query: str,
                      n_results: int = 10) -> List[Dict]:
        """
        Search within a specific library (synchronous).

        Args:
            library_name: Name of library to search
            query: Search query text
            n_results: Maximum number of results to return

        Returns:
            List of search result dictionaries with keys:
            - content: Chunk text content
            - metadata: Chunk metadata (library, file path, etc.)
            - score: Cosine similarity (higher = more similar, 1.0 = identical)
            - library: Library name

        Raises:
            ValueError: If library not found

        Performance: ~100ms for typical query

        Note: This is a synchronous query. Async version deferred to
        1.1 based on real-world demand. For simple systems, 100-500ms
        search is acceptable.

        Example:
            results = orchestrator.search_library(
                library_name="botany",
                query="plant taxonomy classification",
                n_results=10
            )
        """
        # Clear stale connection to force fresh HNSW index load.
        # The sync_worker runs in a separate process and may have
        # deleted/updated chunks in the database. Without clearing,
        # the cached PersistentClient returns stale HNSW results
        # pointing to deleted chunks (metadata=None → crash).
        self.clear_connection(library_name)

        # Get fresh ChromaDB connection
        connection = self.get_connection(library_name)

        # Get library configuration
        library = self.library_manager.get_library(library_name)
        config = self.library_manager.get_library_config(library_name)

        # Get collection name from config
        collection_name = config.get('chromadb', {}).get('collection_name', library_name)

        # Get or create collection
        collection = connection.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine", "library": library_name}
        )

        # Query ChromaDB
        results = collection.query(
            query_texts=[query],
            n_results=n_results
        )

        # Format results
        return self._format_results(results, library_name)

    def search_all_libraries(self, query: str, n_results: int = 10) -> List[Dict]:
        """
        Search across all libraries (synchronous sequential queries).

        Args:
            query: Search query text
            n_results: Maximum number of results to return (total across all libraries)

        Returns:
            List of search result dictionaries, sorted by similarity score

        Performance Characteristics:
        - 10 libraries: ~1000ms (sequential queries)
        - 100 libraries: ~10000ms (may be unacceptable)

        Note: Async parallel queries deferred to 1.1 based on demand.
        For simple systems with few libraries, sequential queries are
        acceptable. Add async parallel search in 1.1 if users report
        performance issues.

        Implementation:
        1. Query each library sequentially
        2. Aggregate all results
        3. Re-rank by similarity score
        4. Return top N results

        Example:
            results = orchestrator.search_all_libraries(
                query="semantic search algorithms",
                n_results=10
            )
        """
        # Get all libraries
        libraries = self.library_manager.list_libraries()

        # Sequential queries (synchronous)
        all_results = []
        for library in libraries:
            library_name = library['name']
            try:
                library_results = self.search_library(library_name, query, n_results)
                all_results.extend(library_results)
            except Exception as e:
                # Log error, continue with other libraries
                print(f"Warning: Search failed for library {library_name}: {e}")
                continue

        # Re-rank by similarity score (higher = more similar)
        all_results.sort(key=lambda x: x['score'], reverse=True)

        # Return top N results
        return all_results[:n_results]

    def get_library_chunks(self, library_name: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Get all chunks from library for keyword filtering.

        Args:
            library_name: Name of library to get chunks from
            limit: Maximum chunks to return (None = all chunks)

        Returns:
            List of chunk dictionaries with keys:
            - id: Chunk ID
            - text: Chunk text content
            - metadata: Chunk metadata (library, file path, etc.)

        Raises:
            ValueError: If library not found

        Purpose:
        This method is used by the keyword search functionality.
        Unlike semantic search which uses vector similarity,
        keyword search retrieves ALL chunks and filters by text matching.

        In the new Blue Sky design:
        - Each library has its own ChromaDB instance
        - No library filtering needed (just get all chunks from library's ChromaDB)
        - Simpler than old design (which had single ChromaDB with library filtering)

        Note: This operation fetches all chunks from the database,
        which can be expensive for large collections (>10,000 chunks).
        Use judiciously.

        Example:
            chunks = orchestrator.get_library_chunks("botany")
            # Then filter chunks using keyword_search(chunks, "plant")
        """
        # Clear stale connection (same reason as search_library)
        self.clear_connection(library_name)

        # Get fresh ChromaDB connection
        connection = self.get_connection(library_name)

        # Get library configuration
        config = self.library_manager.get_library_config(library_name)

        # Get collection name from config
        collection_name = config.get('chromadb', {}).get('collection_name', library_name)

        # Get collection
        collection = connection.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine", "library": library_name}
        )

        # Get all chunks from library
        # Note: No library filtering needed (each library has own ChromaDB)
        all_data = collection.get(limit=limit)

        # Format results
        chunks = []
        for chunk_id, document, metadata in zip(
            all_data.get('ids', []),
            all_data.get('documents', []),
            all_data.get('metadatas', [])
        ):
            # Skip stale entries from deleted chunks
            if document is None:
                continue
            chunks.append({
                'id': chunk_id,
                'text': document,
                'metadata': metadata if metadata is not None else {}
            })

        return chunks

    def _format_results(self, results: Dict, library_name: str) -> List[Dict]:
        """
        Format ChromaDB query results into standardized format.

        Args:
            results: Raw ChromaDB query results
            library_name: Name of library (for tagging)

        Returns:
            List of formatted result dictionaries

        Format:
        {
            'content': str,      # Chunk text content
            'metadata': dict,    # Chunk metadata
            'score': float,      # Cosine similarity (higher = more similar)
            'library': str       # Library name
        }

        Note: Score is cosine similarity (1 - distance). Higher values indicate
        higher similarity (1.0 = identical, 0.0 = orthogonal, negative = opposite).
        """
        formatted = []

        # Extract data from ChromaDB results
        # ChromaDB returns: {ids: [[...]], documents: [[...]], metadatas: [[...]], distances: [[...]]}
        ids = results.get('ids', [])
        documents = results.get('documents', [])
        metadatas = results.get('metadatas', [])
        distances = results.get('distances', [])

        # Handle empty results
        if not ids or not ids[0]:
            return formatted

        # Format each result
        for i, doc in enumerate(documents[0]):
            # Skip stale entries: sync_worker deletes records but HNSW index
            # is not immediately rebuilt, so queries can return IDs for
            # deleted chunks with None content/metadata.
            if doc is None:
                continue

            formatted.append({
                'content': doc,
                'metadata': metadatas[0][i] if metadatas and metadatas[0][i] is not None else {},
                'score': 1 - distances[0][i] if distances else 1.0,
                'library': library_name
            })

        return formatted

    def clear_connection(self, library_name: str):
        """
        Clear cached connection for a library.

        Args:
            library_name: Name of library

        This removes the cached ChromaDB connection for the specified
        library. The connection will be recreated on next use.

        Use this when:
        - ChromaDB instance has been deleted/recreated
        - Connection state is corrupted
        - Testing requires fresh connections

        Note: This is a manual cleanup. Automatic connection cleanup
        (e.g., LRU eviction) is deferred to 1.1 based on demand.
        """
        if library_name in self.connections:
            del self.connections[library_name]

    def clear_all_connections(self):
        """
        Clear all cached ChromaDB connections.

        This removes all cached connections, forcing reconnection on
        next use. Useful for testing or when all ChromaDB instances
        have been modified.

        Note: This is a manual cleanup. Automatic connection cleanup
        is deferred to 1.1 based on demand.
        """
        self.connections.clear()
