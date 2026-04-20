# SPDX-License-Identifier: MIT
#
"""
Abstract backend interface for document storage and retrieval.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class DocumentBackend(ABC):
    """Abstract base class for document backends."""

    @abstractmethod
    def chunk_documents(self, documents: List[str], document_ids: Optional[List[str]] = None, source: str = "upload", library_name: str = None) -> List[Dict]:
        """
        Process documents into chunks with embeddings.

        Args:
            documents: List of document text strings
            document_ids: Optional IDs for tracking
            source: Source identifier
            library_name: Library name for ID prefixing and metadata tagging (Phase 4-3)

        Returns:
            List of created chunks with metadata
        """
        pass

    @abstractmethod
    def query(self, query_text: str, limit: int = 5, library: Optional[str] = None) -> List[Dict]:
        """
        Perform semantic search.

        Args:
            query_text: Search query
            limit: Maximum results
            library: Optional library name to filter search (Phase 4-3)

        Returns:
            List of relevant chunks with scores
        """
        pass

    @abstractmethod
    def delete_documents(self, document_id: str, library: Optional[str] = None) -> int:
        """
        Remove all chunks for a document.

        Args:
            document_id: Document ID to delete
            library: Optional library name (Phase 4-3)

        Returns:
            Number of chunks deleted
        """
        pass

    @abstractmethod
    def get_stats(self) -> Dict:
        """Get backend statistics."""
        pass
