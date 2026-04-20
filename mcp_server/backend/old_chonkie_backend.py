# SPDX-License-Identifier: MIT
#
"""
Chonkie-based document backend.
Uses Chonkie Pipeline for intelligent file-type-aware chunking, ChromaDB for storage.
"""
from typing import List, Dict, Optional
from pathlib import Path
from chonkie import SemanticChunker
from chonkie.embeddings import Model2VecEmbeddings
from model2vec import StaticModel
from .chroma_backend import ChromaBackend
import logging

# Configure logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Enable debug level

# Create console handler with debug level formatting
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')
handler.setFormatter(formatter)

# Add handler to logger if not already added
if not logger.handlers:
    logger.addHandler(handler)


class ChonkieBackend(ChromaBackend):
    """
    Backend using Chonkie Pipeline for intelligent semantic chunking.

    WARNING: This backend is for CHUNKING ONLY. The inherited query(),
    delete_documents(), and get_stats() methods from ChromaBackend have been
    disabled to prevent accidental queries to the global database.

    For search operations, use ChromaDBOrchestrator, which properly handles
    per-library databases. For statistics, use LibraryManager.get_library_stats().
    """

    def __init__(self, collection_name: str = None, db_path: str = None,
                 chunk_size: int = 512, embedding_model: str = "minishlab/potion-base-32M"):
        """
        Initialize Chonkie backend.

        Args:
            collection_name: ChromaDB collection name
            db_path: ChromaDB database path
            chunk_size: Target chunk size in tokens
            embedding_model: Embedding model for semantic chunking

        Note:
            This backend is designed for chunking operations only. Query and
            delete operations are not supported to prevent accidental access to
            the global database singleton.
        """
        super().__init__(collection_name, db_path)

        self.chunk_size = chunk_size
        self.embedding_model = embedding_model

        # Pre-load model with cache enabled (model2vec defaults to force_download=True,
        # which re-downloads 129MB from HuggingFace Hub every time)
        static_model = StaticModel.from_pretrained(self.embedding_model, force_download=False)
        embeddings = Model2VecEmbeddings(model=static_model)

        # Create SemanticChunker once and reuse for all documents
        self.chunker = SemanticChunker(
            chunk_size=self.chunk_size,
            embedding_model=embeddings
        )

    def query(self, *args, **kwargs):
        """
        Disabled method - not supported for ChonkieBackend.

        ChonkieBackend.query() is not supported. Use ChromaDBOrchestrator
        for search queries, which properly handles per-library databases.

        Raises:
            NotImplementedError: Always raised - this method is intentionally disabled.
        """
        raise NotImplementedError(
            "ChonkieBackend.query() is not supported. Use ChromaDBOrchestrator "
            "for search queries, which properly handles per-library databases."
        )

    def delete_documents(self, *args, **kwargs):
        """
        Disabled method - not supported for ChonkieBackend.

        ChonkieBackend.delete_documents() is not supported. Use
        ChromaDBOrchestrator or LibraryManager for document deletion.

        Raises:
            NotImplementedError: Always raised - this method is intentionally disabled.
        """
        raise NotImplementedError(
            "ChonkieBackend.delete_documents() is not supported. Use "
            "ChromaDBOrchestrator or LibraryManager for document deletion."
        )

    def get_stats(self, *args, **kwargs):
        """
        Disabled method - not supported for ChonkieBackend.

        ChonkieBackend.get_stats() is not supported. Use
        LibraryManager.get_library_stats() for statistics.

        Raises:
            NotImplementedError: Always raised - this method is intentionally disabled.
        """
        raise NotImplementedError(
            "ChonkieBackend.get_stats() is not supported. Use "
            "LibraryManager.get_library_stats() for statistics."
        )

    def chunk_documents(self, documents: List[str],
                       document_ids: Optional[List[str]] = None,
                       source: str = "upload",
                       library_name: str = None) -> List[Dict]:
        """
        Process documents using Chonkie semantic chunking (legacy interface).

        DEPRECATED: Use chunk_files() instead for file-type-aware processing.
        This method processes pre-extracted text and applies semantic chunking.

        Args:
            documents: List of document text strings
            document_ids: Optional IDs for tracking
            source: Source identifier
            library_name: REQUIRED - Library name for ID prefixing and metadata tagging (Phase 4-3)

        Returns:
            List of created chunks with metadata

        Note:
            Phase 4-3: Chunk IDs are prefixed with library_name to ensure global uniqueness.
            Format: {library_name}_{document_id}_chunk_{index}
        """
        if library_name is None:
            raise ValueError("library_name parameter is required for chunk_documents")

        # [PHASE 2 LOGGING] Entry point - log the chunking operation start
        logger.info(f"[CHUNK_FILES] Starting chunking operation")
        logger.debug(f"[CHUNK_FILES] Parameters: file_paths={len(file_paths)} files, source='{source}', library_name='{library_name}'")
        logger.debug(f"[CHUNK_FILES] File paths to process:")
        for fp in file_paths:
            logger.debug(f"  - {fp}")

        if not document_ids:
            import uuid
            document_ids = [str(uuid.uuid4()) for _ in documents]

        collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        processed_chunks = []

        for doc_id, doc_text in zip(document_ids, documents):
            # Reuse cached SemanticChunker instance
            chunks = self.chunker(doc_text)

            for chunk_idx, chunk in enumerate(chunks):
                if not chunk.text.strip():
                    continue

                # CRITICAL: Prefix ID with library name to ensure global uniqueness (Phase 4-3)
                chunk_id = f"{library_name}_{doc_id}_chunk_{chunk_idx}"
                metadata = {
                    "library": library_name,        # NEW: Library identifier for filtering
                    "document_id": doc_id,         # Keep original doc_id for reference
                    "source": source,               # Source file/path
                    "chunk_index": chunk_idx,
                    "token_count": chunk.token_count,
                    "char_count": len(chunk.text),
                    "chunking_method": "chonkie_semantic"
                }

                try:
                    collection.add(
                        documents=[chunk.text],
                        ids=[chunk_id],
                        metadatas=[metadata]
                    )

                    processed_chunks.append({
                        "id": chunk_id,
                        "text": chunk.text,
                        "metadata": metadata
                    })
                except Exception as e:
                    print(f"Error adding chunk {chunk_id}: {e}")
                    continue

        return processed_chunks

    def chunk_files(self, file_paths: List[str], source: str = "upload", library_name: str = None) -> List[Dict]:
        """
        Process files using Chonkie with file-type-aware processing.

        This is the RECOMMENDED method for indexing files. It uses Chonkie's
        SemanticChunker for intelligent semantic chunking:
        - Markdown (.md): Process as markdown, then semantic chunking
        - Text (.txt, .rst): Process as text, then semantic chunking
        - Code (.py, .js, .ts): Process as code, then semantic chunking
        - Shell Scripts (.sh, .bash): Process as text, then semantic chunking
        - HTML (.html): Convert to Markdown via html2text, then semantic chunking

        WARNING: Binary files (PDF, DOCX, images, etc.) are filtered
        by shadow_manager and should not reach this method. If they do,
        they will be skipped with a warning.

        For best results, pre-convert binaries to markdown before creating library.
        See installer_guide.md for pre-conversion workflow.

        Args:
            file_paths: List of file paths to process
            source: Source identifier (e.g., library path)
            library_name: REQUIRED - Library name for ID prefixing and metadata tagging (Phase 4-3)

        Returns:
            List of created chunks with metadata

        Note:
            Phase 4-3: Chunk IDs are prefixed with library_name to ensure global uniqueness.
            Format: {library_name}_{document_id}_chunk_{index}
        """
        if library_name is None:
            raise ValueError("library_name parameter is required for chunk_files")
        import uuid
        # Get collection
        collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        processed_chunks = []

        for file_path in file_paths:
            path_obj = Path(file_path)
            # [PHASE 2 LOGGING] File processing entry - log each file being processed
            logger.debug(f"[CHUNK_FILES] Processing file: {file_path}")
            
            if not path_obj.exists():
                logger.warning(f"[CHUNK_FILES] File not found: {file_path}")
                print(f"Warning: File not found: {file_path}")
                continue


            # Extract text based on file type
            ext = path_obj.suffix.lower()
            try:
                # ONLY PROCESS TEXT FILES - binaries should be filtered by shadow manager
                if ext in ('.md', '.txt', '.rst', '.log'):
                    # Process as text
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        text = f.read()
                elif ext in ('.py', '.js', '.ts', '.sh', '.bash', '.zsh'):
                    # Process as code/shell
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        text = f.read()
                elif ext in ('.json', '.yaml', '.yml', '.toml'):
                    # Process as config
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        text = f.read()
                elif ext == '.html':
                    # Convert HTML to Markdown before chunking
                    import html2text
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        raw_html = f.read()
                    h = html2text.HTML2Text()
                    h.ignore_links = False   # Preserve links as markdown
                    h.ignore_images = True    # Skip images (no binary in text pipeline)
                    h.body_width = 0          # No line wrapping
                    text = h.handle(raw_html)
                else:
                    # Binary file - should not reach here if shadow manager did its job
                    print(f"Warning: Unsupported file type {ext} - skipping {file_path}")
                    print(f"  Binary files should be filtered by shadow_manager")
                    print(f"  See installer_guide.md for pre-conversion workflow")
                    continue

                if not text.strip():
                    print(f"Warning: No text extracted from {file_path}")
                    continue

                # Check if file was deleted from filesystem (BUG-002 fix)
                file_deleted = file_path not in metadata or metadata.get(file_path, {}).get('deleted', False)
                
                if file_deleted:
                    # ===== POINT A: FILE DELETION DETECTION LOGGING =====
                    logger.info(f"[CHUNK_FILES] File deleted from filesystem: {file_path}")
                    logger.debug(f"[CHUNK_FILES] Cleaning up orphaned chunks for: {file_path}")

                # Delete existing chunks for this file before re-indexing (BUG-002 fix)
                try:
                    existing = collection.get(
                        where={"source": str(path_obj)},
                        limit=None
                    )
  
                    if existing['ids']:
                            # ===== POINT C: CLEANUP ATTEMPT LOGGING =====
                            logger.info(f"[CHUNK_FILES] Deleting {len(existing['ids'])} orphaned chunks for {file_path}")
                            
                            collection.delete(ids=existing['ids'])
                            
                            # ===== POINT C: CLEANUP SUCCESS LOGGING =====
                            if existing['ids']:
                                logger.info(f"[CHUNK_FILES] Successfully deleted {len(existing['ids'])} orphaned chunks for {file_path}")
                            else:
                                logger.debug(f"[CHUNK_FILES] No chunks found to delete for {file_path}")
                    else:
                            # ===== POINT C: NO CHUNKS FOUND LOGGING =====
                            logger.debug(f"[CHUNK_FILES] No existing chunks found for {file_path} (no cleanup needed)")
                    except Exception as e:
                        # ===== POINT C: EXCEPTION HANDLING LOGGING =====
                        logger.error(f"[CHUNK_FILES] Failed to delete chunks for {file_path}: {e}")
                        logger.error(f"[CHUNK_FILES] Error type: {type(e).__name__}")
                    else:
                    # File exists in metadata - proceed with normal re-indexing
                    try:
                        existing = collection.get(
                            where={"source": str(path_obj)},
                            limit=None
                        )
                        if existing['ids']:
                            logger.info(f"[CHUNK_FILES] Old chunks detected: {len(existing['ids'])} chunks to delete")
                            logger.debug(f"[CHUNK_FILES] Existing chunk IDs: {existing['ids'][:5]}{'...' if len(existing['ids']) > 5 else ''}")
                            
                            collection.delete(ids=existing['ids'])
                            logger.info(f"[CHUNK_FILES] Successfully deleted {len(existing['ids'])} old chunks for {file_path}")
                            print(f"Removed {len(existing['ids'])} old chunks for {file_path}")
                        else:
                            logger.debug(f"[CHUNK_FILES] No existing chunks found for {file_path} (first index)")
                    except Exception as e:
                        logger.warning(f"[CHUNK_FILES] Could not remove old chunks for {file_path}: {e}")
                        print(f"Warning: Could not remove old chunks for {file_path}: {e}")
  


                # Chunk the text using cached SemanticChunker
                doc_id = str(uuid.uuid4())
                logger.debug(f"[CHUNK_FILES] Generated document ID: {doc_id[:12]}...")
                chunks = self.chunker(text)
                logger.debug(f"[CHUNK_FILES] Chonkie produced {len(chunks)} chunks for {file_path}")

                for chunk_idx, chunk in enumerate(chunks):
                    if not chunk.text.strip():
                        continue

                    # CRITICAL: Prefix ID with library name to ensure global uniqueness (Phase 4-3)
                    chunk_id = f"{library_name}_{doc_id}_chunk_{chunk_idx}"
                    metadata = {
                        "library": library_name,  # NEW: Library identifier for filtering
                        "chunk_index": chunk_idx,
                        "document_id": doc_id,
                        "document_name": path_obj.name,
                        "source": str(path_obj),
                        "token_count": chunk.token_count,
                        "char_count": len(chunk.text),
                        "chunking_method": "chonkie_semantic",
                        "file_type": ext
                    }

                    logger.debug(f"[CHUNK_FILES] Creating chunk {chunk_idx + 1}/{len(chunks)}: {chunk_id}")
                    logger.debug(f"[CHUNK_FILES]   Token count: {chunk.token_count}, Char count: {len(chunk.text)}")

                    try:
                        collection.add(
                            documents=[chunk.text],
                            ids=[chunk_id],
                            metadatas=[metadata]
                        )

                        processed_chunks.append({
                            "id": chunk_id,
                            "text": chunk.text,
                            "metadata": metadata
                        })
                        
                        if chunk_idx == 0:
                            logger.info(f"[CHUNK_FILES] Added first chunk for {file_path}")
                    except Exception as e:
                        logger.error(f"[CHUNK_FILES] Error adding chunk {chunk_id}: {e}")
                        print(f"Error adding chunk {chunk_id}: {e}")
                        continue

                # Log completion of chunking for this file
                if processed_chunks:
                    logger.info(f"[CHUNK_FILES] Successfully created {len(processed_chunks)} chunks for {file_path}")


            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                continue

        # [PHASE 2 LOGGING] Summary of chunking operation
        logger.info(f"[CHUNK_FILES] Chunking operation complete")
        if processed_chunks:
            logger.info(f"[CHUNK_FILES] Total chunks created: {len(processed_chunks)}")
        else:
            logger.warning("[CHUNK_FILES] No chunks were created (all files may have been skipped)")


        return processed_chunks

    def get_backend_info(self) -> Dict:
        """Get information about the backend configuration."""
        return {
            "backend_type": "chonkie",
            "chunking_method": "semantic_pipeline",
            "chunk_size": self.chunk_size,
            "embedding_model": self.embedding_model,
            "collection_name": self.collection_name,
            "db_path": self.db_path,
            "file_type_aware": True,
            "supported_extensions": [
                ".md", ".txt", ".rst", ".log",
                ".py", ".js", ".ts", ".sh", ".bash", ".zsh",
                ".json", ".yaml", ".yml", ".toml",
                ".html"
            ]
        }
