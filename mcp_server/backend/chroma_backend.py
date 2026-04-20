# SPDX-License-Identifier: MIT
#
"""
ChromaDB backend implementation.
"""
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from .base import DocumentBackend


class ChromaBackend(DocumentBackend):
    """ChromaDB backend for per-library document storage and retrieval."""

    def __init__(self, collection_name: str, db_path: str):
        """
        Initialize ChromaDB backend for a specific library.

        Args:
            collection_name: Name of the ChromaDB collection (required)
            db_path: Path to per-library ChromaDB directory (required)

        Blue Sky: Each library has its own ChromaDB at .librarian/chromadb/.
        Both parameters are required — there is no global fallback.
        """
        if not collection_name:
            raise ValueError("collection_name is required (per-library architecture)")
        if not db_path:
            raise ValueError("db_path is required (per-library architecture)")

        self.collection_name = collection_name
        self.db_path = db_path

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        self._ensure_collection()

        # Stats cache - temporarily disabled to debug segfault
        # self._stats_cache = None
        # self._stats_cache_time = None

    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        try:
            self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            print(f"Warning: Could not ensure collection exists: {e}")

    def chunk_documents(self, documents: List[str], document_ids: Optional[List[str]] = None, source: str = "upload", library_name: str = None) -> List[Dict]:
        """
        Process documents into chunks with embeddings.

        Args:
            documents: List of document text strings
            document_ids: Optional IDs for tracking
            source: Source identifier
            library_name: REQUIRED - Library name for ID prefixing and metadata tagging

        Returns:
            List of created chunks with metadata

        Note:
            Phase 4-3: Chunk IDs are prefixed with library_name to ensure global uniqueness.
            Format: {library_name}_{document_id}_chunk_{index}
            Example: "botany_README.md_chunk_0"
        """
        if library_name is None:
            raise ValueError("library_name parameter is required for chunk_documents")

        if not document_ids:
            import uuid
            document_ids = [str(uuid.uuid4()) for _ in documents]

        collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        # Collect all chunks first for batch operation
        all_chunks = []
        all_ids = []
        all_metadatas = []
        processed_chunks = []

        for doc_id, doc_text in zip(document_ids, documents):
            # Simple sentence-based chunking
            chunks = self._chunk_text(doc_text)

            for chunk_idx, chunk_text in enumerate(chunks):
                if not chunk_text.strip():
                    continue

                # CRITICAL: Prefix ID with library name to ensure global uniqueness (Phase 4-3)
                # This prevents ID collisions when same filename exists in multiple libraries
                chunk_id = f"{library_name}_{doc_id}_chunk_{chunk_idx}"
                metadata = {
                    "library": library_name,        # NEW: Library identifier for filtering
                    "document_id": doc_id,         # Keep original doc_id for reference
                    "source": source,               # Source file/path
                    "chunk_index": chunk_idx
                }

                all_chunks.append(chunk_text)
                all_ids.append(chunk_id)
                all_metadatas.append(metadata)

                # Track for return value
                processed_chunks.append({
                    "id": chunk_id,
                    "text": chunk_text,
                    "metadata": metadata
                })

        # Batch add all chunks at once (much more efficient)
        if all_chunks:
            try:
                collection.add(
                    documents=all_chunks,
                    ids=all_ids,
                    metadatas=all_metadatas
                )
            except Exception as e:
                print(f"Error adding chunks in batch: {e}")
                # Fall back to individual adds if batch fails
                for i, (chunk_text, chunk_id, metadata) in enumerate(zip(all_chunks, all_ids, all_metadatas)):
                    try:
                        collection.add(
                            documents=[chunk_text],
                            ids=[chunk_id],
                            metadatas=[metadata]
                        )
                    except Exception as e2:
                        print(f"Error adding chunk {chunk_id}: {e2}")
                        # Remove from processed_chunks if it failed
                        processed_chunks = [c for c in processed_chunks if c['id'] != chunk_id]

        return processed_chunks

    def _chunk_text(self, text: str, chunk_size: int = None) -> List[str]:
        """
        Split text into chunks.

        Args:
            text: Text to chunk
            chunk_size: Target chunk size in characters

        Returns:
            List of text chunks
        """
        from ..config.settings import settings

        chunk_size = chunk_size or settings.CHUNK_SIZE

        if not text or len(text) <= chunk_size:
            return [text] if text else []

        # Simple sentence-based chunking
        chunks = []
        current_chunk = []

        # Split by sentences (rough approximation)
        sentences = text.split('. ')

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Add period back if it's not the last sentence
            if current_chunk or len(current_chunk) > 0:
                test_text = '. '.join(current_chunk + [sentence])
            else:
                test_text = sentence

            if len(test_text) > chunk_size and current_chunk:
                # Current chunk is full, save it
                chunks.append('. '.join(current_chunk))
                current_chunk = [sentence]
            else:
                current_chunk.append(sentence)

        # Don't forget the last chunk
        if current_chunk:
            chunks.append('. '.join(current_chunk))

        return chunks

    def query(self, query_text: str, limit: int = 5, library: Optional[str] = None) -> List[Dict]:
        """
        Perform semantic search.

        Args:
            query_text: Search query
            limit: Maximum results
            library: Optional library name to filter search (Phase 4-3)

        Returns:
            List of relevant chunks with scores

        Note:
            Phase 4-3: When library is specified, search is filtered to that library only.
            When library is None, search across all libraries.
        """
        collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        # Build where clause for library filtering (Phase 4-3)
        where_clause = {"library": library} if library else None

        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=limit,
                where=where_clause
            )
        except Exception as e:
            print(f"Query error: {e}")
            return []

        formatted = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metadatas = results.get("metadatas", [{}])[0]
            distances = results.get("distances", [])[0]
            ids = results.get("ids", [])[0]

            for i, doc in enumerate(docs):
                formatted.append({
                    "chunk_id": ids[i] if i < len(ids) else f"unknown-{i}",
                    "text": doc,
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "similarity_score": 1 / (distances[i] + 1e-8) if i < len(distances) else 0.0,
                    "rank": i + 1
                })

        return formatted

    def delete_documents(self, document_id: str, library: Optional[str] = None) -> int:
        """
        Remove all chunks for a document.

        Args:
            document_id: Document ID to delete (can be prefixed or base ID)
            library: Optional library name (required if document_id is not prefixed)

        Returns:
            Number of chunks deleted

        Note:
            Phase 4-3: Supports two ID formats:
            1. Prefixed IDs: "botany_README.md" (deletes from specific library)
            2. Base IDs: "README.md" (requires library parameter)

            The optimized implementation avoids expensive get_stats() calls by using direct ID lookup first.
        """
        collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        try:
            # OPTIMIZATION: Try direct ID lookup first (avoids expensive get_stats() call)
            # Step 1: Try to find the ID directly (Most Efficient)
            results = collection.get(ids=[document_id], limit=None)

            if results['ids']:
                # ID exists in DB. Verify library match if specified
                if library:
                    for metadata in results['metadatas']:
                        if metadata.get('library') != library:
                            raise ValueError(
                                f"Document '{document_id}' exists in library "
                                f"'{metadata.get('library')}', not '{library}'"
                            )

                # Delete directly by ID (fast path)
                collection.delete(ids=results['ids'])
                print(f"Deleted {len(results['ids'])} chunks for document {document_id}")
                return len(results['ids'])

            # Step 2: ID not found. Assume it is a base document_id (e.g., "README.md")
            # Requires library parameter for safety
            if not library:
                raise ValueError(
                    f"Document ID '{document_id}' not found. "
                    f"If using a base document_id (without library prefix), "
                    f"you must specify the 'library' parameter."
                )

            # Query by metadata with library filter using $and operator
            where_clause = {
                "$and": [
                    {"document_id": document_id},
                    {"library": library}
                ]
            }
            results = collection.get(where=where_clause, limit=None)

            if results['ids']:
                collection.delete(ids=results['ids'])
                print(f"Deleted {len(results['ids'])} chunks for document {document_id} in library {library}")
                return len(results['ids'])
            else:
                print(f"No chunks found for document {document_id} in library {library}")
                return 0

        except ValueError:
            raise
        except Exception as e:
            print(f"Error deleting document {document_id}: {e}")
            return 0

    def get_stats(self) -> Dict:
        """
        Get backend statistics.

        Returns:
            Dictionary with backend statistics including per-library breakdown

        Warning:
            This operation fetches all metadata from the database, which can be expensive
            for large collections (>10,000 chunks). Consider caching the results if calling
            this frequently.
        """
        collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        total_chunks = collection.count()

        # Get all metadata for per-library breakdown (expensive for large collections)
        all_data = collection.get()

        # Count chunks and documents per library
        library_chunks = {}
        library_documents = {}

        for metadata in all_data.get('metadatas', []):
            lib = metadata.get('library', 'unknown')
            doc_id = metadata.get('document_id', 'unknown')

            # Count chunks
            library_chunks[lib] = library_chunks.get(lib, 0) + 1

            # Count unique documents
            if lib not in library_documents:
                library_documents[lib] = set()
            library_documents[lib].add(doc_id)

        # Convert sets to counts
        library_document_counts = {lib: len(docs) for lib, docs in library_documents.items()}

        return {
            "backend": "chromadb",
            "collection": self.collection_name,
            "total_chunks": total_chunks,
            "total_documents": sum(library_document_counts.values()),
            "libraries": sorted(library_chunks.keys()),
            "library_chunks": library_chunks,
            "library_documents": library_document_counts,
            "db_path": self.db_path
        }

    def get_library_chunks(self, library: str = None, limit: int = None) -> List[Dict]:
        """
        Get all chunks for a library (for keyword filtering).

        Args:
            library: Library name to filter (if None, returns all chunks)
            limit: Maximum chunks to return (if None, returns all)

        Returns:
            List of all chunks with text and metadata

        Note:
            This operation fetches all chunks from the database, which can be expensive
            for large collections (>10,000 chunks). Use judiciously.
        """
        collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        # Build where clause for library filtering
        where_clause = {"library": library} if library else None

        # Get all chunks (expensive for large collections!)
        all_data = collection.get(where=where_clause, limit=limit)

        # Format results
        chunks = []
        for chunk_id, document, metadata in zip(
            all_data.get('ids', []),
            all_data.get('documents', []),
            all_data.get('metadatas', [])
        ):
            chunks.append({
                "id": chunk_id,
                "text": document,
                "metadata": metadata
            })

        return chunks

    def clear(self) -> bool:
        """
        Clear all documents from the collection.

        Returns:
            True if successful, False otherwise
        """
        try:
            collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )

            # Get current count
            count = collection.count()

            if count > 0:
                # Get all document IDs
                all_data = collection.get()
                all_ids = all_data.get('ids', [])

                if all_ids:
                    # Delete all documents by ID
                    collection.delete(ids=all_ids)
                    print(f"Cleared {len(all_ids)} chunks from collection '{self.collection_name}'")
                else:
                    print(f"Collection '{self.collection_name}' is already empty")
            else:
                print(f"Collection '{self.collection_name}' is already empty")

            return True

        except Exception as e:
            print(f"Error clearing collection: {e}")
            return False
