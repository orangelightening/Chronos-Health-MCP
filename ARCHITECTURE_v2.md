# Librarian MCP Server — Architecture (Blue Sky v2)

**Version**: 1.0 (Blue Sky)  
**Date**: 2026-04-21 (v4 — dashboard, macOS support, CPU-only requirements)  
**Status**: Current

---

## Overview

The **Librarian MCP Server** is a Model Context Protocol (MCP) server that enables AI models to act as intelligent librarians with semantic document search capabilities across **multiple independent libraries**.

**Architecture**: Blue Sky — in-place indexing, per-library ChromaDB, no shadow copies.

**Key Features**:
- ✅ **In-Place Indexing** — Documents indexed where they live, no copies
- ✅ **Per-Library ChromaDB** — Each library has its own isolated vector database
- ✅ **Dynamic CLI Security** — CLI tools validated against registered library roots
- ✅ **Central Report Location** — All reports written to `/home/user/.librarian/`, with optional per-library delivery to `library/delivery/` for distributed setups
- ✅ **Text-Only Pipeline** — Only text files indexed, no binary support
- ✅ **Incremental Sync** — SHA-256 checksum-based change detection
- ✅ **Multi-Mode Operation** — Three server modes with different tool sets
- ✅ **Web Dashboard** — Read-only status page showing servers and libraries at a glance
- ✅ **Semantic Chunking** — Chonkie SemanticChunker for all file types (file-type-aware chunking planned for Release 1.1)
- ✅ **Distributed Libraries (Optional)** — Syncthing over Tailscale mirrors libraries to remote devices with document delivery
- ✅ **Unified Cleanup Phase** — Indexer owns all chunk deletion (file deletion + update cleanup)

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI Model Chat Window                          │
│                  (MCP Client: Jan / LM Studio)             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Multi-Mode Librarian MCP Servers                   │
│                   (4 Separate Processes)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐     │
│  │ LibraryManager │  │  LibraryUser   │  │     Admin      │     │
│  │   Port 8889    │  │   Port 8890    │  │   Port 8891    │     │
│  │   18 tools     │  │   14 tools     │  │   All tools    │     │
│  └────────┬───────┘  └────────┬───────┘  └────────┬───────┘     │
│           └───────────────────┼───────────────────┘              │
│                               │                                  │
│  ┌────────────────────────────┼──────────────────────────────┐  │
│  │                            ▼                              │  │
│  │  ┌───────────────────────────────────────────────┐       │  │
│  │  │         Core Business Logic                   │       │  │
│  │  │                                               │       │  │
│  │  │  ┌─────────────────────────────────────────┐  │       │  │
│  │  │  │ LibraryManager                          │  │       │  │
│  │  │  │ • Library registry (libraries.yaml)     │  │       │  │
│  │  │  │ • Register / unregister libraries       │  │       │  │
│  │  │  │ • Load per-library config.yaml          │  │       │  │
│  │  │  └─────────────────────────────────────────┘  │       │  │
│  │  │  ┌─────────────────────────────────────────┐  │       │  │
│  │  │  │ Indexer                                 │  │       │  │
│  │  │  │ • In-place file scanning                │  │       │  │
│  │  │  │ • SHA-256 change detection              │  │       │  │
│  │  │  │ • Incremental / full re-index           │  │       │  │
│  │  │  │ • Chunk lifecycle (delete + update)     │  │       │  │
│  │  │  │ • .librarianignore integration          │  │       │  │
│  │  │  └─────────────────────────────────────────┘  │       │  │
│  │  │  ┌─────────────────────────────────────────┐  │       │  │
│  │  │  │ ChromaDBOrchestrator                    │  │       │  │
│  │  │  │ • Per-library ChromaDB connections      │  │       │  │
│  │  │  │ • Single / cross-library search         │  │       │  │
│  │  │  │ • Keyword search support                │  │       │  │
│  │  │  └─────────────────────────────────────────┘  │       │  │
│  │  │  ┌─────────────────────────────────────────┐  │       │  │
│  │  │  │ LibraryStatus                           │  │       │  │
│  │  │  │ • Atomic status updates                 │  │       │  │
│  │  │  │ • Active flag for sync locking          │  │       │  │
│  │  │  └─────────────────────────────────────────┘  │       │  │
│  │  └───────────────────────────────────────────────┘       │  │
│  │                                                           │  │
│  │  ┌───────────────────────────────────────────────┐       │  │
│  │  │         Backend Layer                         │       │  │
│  │  │  ┌───────────────────────────────────────┐    │       │  │
│  │  │  │  ChonkieBackend                       │    │       │  │
│  │  │  │  • SemanticChunker (all file types)   │    │       │  │
│  │  │  │  • Per-library collection             │    │       │  │
│  │  │  │  • Binary screening by extension      │    │       │  │
│  │  │  │  • Pure insert (no delete logic)       │    │       │  │
│  │  │  └───────────────────────────────────────┘    │       │  │
│  │  └───────────────────────────────────────────────┘       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│ botany/      │  │ martha-health│  │ /home/peter/         │
│ └── .librarian│  │ └── .librarian│  │ └── .librarian/     │
│     └── chromadb│     └── chromadb│      (Reports only)  │
│ └── delivery/ │  │ └── delivery/ │  └──────────────────────┘
└──────────────┘  └──────────────┘
  Per-library DB    Per-library DB     Central write location
                                      (delivery/ synced to remote
                                       devices via Syncthing)
```

---

## Multi-Mode Server Architecture

Three server modes with different tool sets:

| Mode | Port | Tools | Purpose |
|------|------|-------|---------|
| **LibraryManager** | 8889 | 18 | Library administration + search |
| **LibraryUser** | 8890 | 14 | Search, browse, write reports |
| **Admin** | 8891 | All (incl. admin_command) | Full system control |

**Why Multi-Mode?**
 - Smaller tool sets improve LLM tool selection accuracy (14 vs 22+ tools)
- Security: end users can't rebuild libraries or run admin commands
- Principle of least privilege

**Admin-only tool:** `admin_command` provides expanded command whitelist (`ps`, `pip`, `env`, `printenv`, `which`) with broader path scope (library roots + project source). Argument guards block write operations (`pip install`, `ps -k`, etc.).

---

## Dashboard Architecture

The dashboard is a standalone FastAPI application on port 8892 — separate from the three MCP servers. It serves humans, not AI clients.

```
┌──────────────┐  ┌──────────────┐
│   Browser    │  │  MCP Client  │
│  (human)     │  │  (AI)        │
└──────┬───────┘  └──────┬───────┘
       │                 │
       ▼                 ▼
┌──────────────┐  ┌──────────────────────┐
│  Dashboard   │  │  MCP Servers         │
│  :8892       │  │  :8889 :8890 :8891   │
│  (FastAPI)   │  │  (FastMCP)           │
└──────┬───────┘  └──────┬───────────────┘
       │                 │
       └────────┬────────┘
                ▼
   ┌─────────────────────────┐
   │  Shared Python Classes  │
   │  LibraryManager         │
   │  LibraryStatus          │
   │  PID files, logs        │
   └─────────────────────────┘
```

**Why separate from MCP?**
- Dashboard serves humans, MCP serves AI clients — different audiences
- Crash isolation — dashboard restart doesn't affect MCP servers
- Different lifecycle — can be developed and deployed independently
- No privilege confusion — dashboard is an observer, not a mode

**Phase 1 (Current — Read-Only):**
- Server status: running/stopped, port, uptime for all three modes
- Library status: registered libraries with doc/chunk counts, last sync time
- Broken library detection
- Auto-refresh every 30 seconds
- Accessible at `http://localhost:8892` or `http://100.x.y.z:8892` over Tailscale

**Phase 2 (Planned — Read-Write):**
- Start/stop server controls
- Sync/rebuild library triggers
- Persistence toggle (systemd auto-start)

### Dashboard API Endpoints

| Endpoint | Method | Returns |
|----------|--------|--------|
| `/` | GET | Dashboard HTML page |
| `/api/status` | GET | JSON: servers + libraries combined |
| `/api/servers` | GET | JSON: server status array |
| `/api/libraries` | GET | JSON: library status array |

---

## Indexing Pipeline

### Five Stages

The indexing pipeline transforms source files on disk into searchable vector embeddings stored in per-library ChromaDB instances. Each stage has a clear responsibility.

```
┌─────────────┐    ┌─────────────┐    ┌──────────────────┐    ┌─────────────┐    ┌─────────────┐
│  1. FETCH    │───▶│  2. SCREEN  │───▶│  3. CHUNK        │───▶│  4. EMBED   │───▶│  5. STORE   │
│              │    │             │    │                  │    │             │    │             │
│ Discover     │    │ Text only?  │    │ SemanticChunker  │    │ ChromaDB    │    │ Per-library │
│ files on     │    │ Extension   │    │ splits at        │    │ generates   │    │ ChromaDB    │
│ disk         │    │ check       │    │ semantic         │    │ similarity  │    │ instance    │
│              │    │             │    │ boundaries       │    │ vectors     │    │             │
└─────────────┘    └─────────────┘    └──────────────────┘    └─────────────┘    └─────────────┘
      Indexer           Indexer          ChonkieBackend         ChromaDB           ChromaDB
   ._discover_files   in chunk_files   .chunk_files()        auto on .add()    auto on .add()
```

### Stage 1: Fetch (Document Discovery)

**Component**: `Indexer._discover_files()`  
**Input**: Library root path, config.yaml file type patterns  
**Output**: List of file paths to index

Scans the library root recursively for files matching configured patterns (`*.md`, `*.py`, etc.). Files in `.librarian/` are always skipped. Files matching `.librarianignore` patterns are skipped.

### Stage 2: Screen (Binary Rejection)

**Component**: `ChonkieBackend.chunk_files()`  
**Input**: File path  
**Output**: Raw text content, or skip

Each file's extension is checked against the known text types. This is a two-level screen:
1. **Discovery level** (Indexer) — only files matching configured patterns are found at all
2. **Read level** (Backend) — extension check as safety net, then `f.read()` to extract text

HTML files (`.html`) undergo an additional conversion step: raw HTML is read, then converted to clean Markdown via `html2text` before reaching the chunker. Links are preserved as markdown, images are skipped (no binary in text pipeline), and line wrapping is disabled. The `file_type` metadata field retains `.html` for source format traceability.

Binary files (PDF, DOCX, images) are rejected with a warning. Only text files proceed.

### Stage 3: Chunk (Semantic Splitting)

**Component**: `ChonkieBackend` — `SemanticChunker`  
**Input**: Full text of one file  
**Output**: List of chunk objects with text, token counts, positions

The `SemanticChunker` from Chonkie:
1. Splits text into sentences
2. Computes embeddings for each sentence (`minishlab/potion-base-32M`)
3. Groups consecutive sentences with similar meaning into chunks
4. Respects `chunk_size` limit (512 tokens default)

**Model caching**: The `potion-base-32M` model is pre-loaded in `ChonkieBackend.__init__()` with `force_download=False`, which uses the locally cached copy from `~/.cache/huggingface/hub/`. This avoids a 129MB re-download from HuggingFace Hub on every sync worker invocation. The loaded `Model2VecEmbeddings` object is passed directly to `SemanticChunker` instead of the model name string.

**Release 1.0**: SemanticChunker is used for ALL file types — markdown, code, config, plain text. It produces good results across all types because it splits where meaning shifts, not just at structural boundaries.

**Release 1.1 (planned)**: File-type-aware chunker selection:

| File Type | Release 1.0 | Release 1.1 (planned) | Why |
|-----------|-------------|----------------------|-----|
| `.md` | SemanticChunker | MarkdownChunker | Splits on headers, preserves section structure |
| `.py`, `.js`, `.ts` | SemanticChunker | CodeChunker | Splits on function/class boundaries |
| `.txt`, `.rst` | SemanticChunker | SemanticChunker | Already optimal for prose |
| `.yaml`, `.json` | SemanticChunker | Token-based or SentenceChunker | Config files are typically short |

**Why deferred**: SemanticChunker produces good results for all types. The improvement from file-type-specific chunkers is incremental, not fundamental. Current bugs are higher priority.

### Stage 4: Embed (Vector Generation)

**Component**: ChromaDB (automatic on `collection.add()`)  
**Input**: Chunk text  
**Output**: Similarity vector stored alongside chunk

Two embedding operations happen during the pipeline, for different purposes:

```
1. Chonkie embedding (potion-base-32M)
   Purpose: Decide WHERE to split text (semantic boundaries)
   When: During Stage 3 (chunking)
   Stored: No — only used for chunk boundary decisions

2. ChromaDB embedding (default model)
   Purpose: Enable similarity search queries
   When: During Stage 5 (storage), auto-generated by collection.add()
   Stored: Yes — the vector used for search
```

These can use different models because they serve different purposes. The search quality depends on ChromaDB's embedding model, not Chonkie's.

### Stage 5: Store (Per-Library ChromaDB)

**Component**: `ChromaBackend` (via ChonkieBackend inheritance)  
**Input**: Chunk text, metadata, ID  
**Output**: Persistent storage in library's ChromaDB

Each chunk is stored with rich metadata:

| Field | Purpose | Example |
|-------|---------|---------|
| `documents` | Full chunk text (doubles as keyword search source) | `"# Oak Trees\nOak trees are..."` |
| `ids` | Globally unique ID | `botany_uuid_chunk_3` |
| `library` | Library name for filtering | `botany` |
| `document_id` | UUID for document lifecycle | `a1b2c3d4-...` |
| `document_name` | Filename for display | `oak.md` |
| `source` | Full file path for lifecycle management | `/home/peter/botany/plants/oak.md` |
| `chunk_index` | Position in document | `3` |
| `total_chunks` | Total chunks for this document | `12` |
| `file_type` | Extension for display | `.md` |
| `token_count` | Tokens in this chunk | `487` |
| `chunking_method` | How it was chunked | `chonkie_semantic` |

---

## Search Architecture

### Semantic Search

```
search_library(query="plant taxonomy", library="botany", limit=10)
    │
    ▼
ChromaDBOrchestrator.search_library()
    │
    ├── Get/create ChromaDB connection for "botany"
    │   └── /home/peter/botany/.librarian/chromadb/
    ├── Get collection "botany"
    ├── collection.query(query_texts=["plant taxonomy"], n_results=10)
    │   └── ChromaDB embeds query → finds nearest vectors → returns chunks
    │
    ├── Convert cosine distance to similarity: score = 1 - distance
    │   (1.0 = identical, 0.0 = unrelated, higher is better)
    │
    └── Format results with scores and metadata (sorted descending by score)
```

**Cross-library search** queries each library sequentially, aggregates results, re-ranks by score.

### Keyword Search

Keyword search reuses the chunk text stored in ChromaDB. No separate index needed.

```
search_library_keyword(keyword="Garry oak", library="botany")
    │
    ▼
ChromaDBOrchestrator.get_library_chunks("botany")
    │
    ├── collection.get() → retrieves ALL chunks from library's ChromaDB
    │   Returns: ids, documents, metadatas
    │
    ▼
keyword_search(chunks=all_chunks, keyword="Garry oak")
    │
    ├── For each chunk: substring match (case-insensitive by default)
    │   ├── Match → count occurrences, add to results
    │   └── No match → skip
    │
    ├── Sort by match count (most matches first)
    │
    └── Return formatted results with snippets around first match
```

**Performance**: Acceptable up to ~50,000 chunks per library. Beyond that, a dedicated keyword index would be needed (Release 1.1).

---

## Sync Architecture

### Incremental Sync (sync_library_async)

```
sync_library_async(library="botany")
    │
    ├── Set active flag in config.yaml (prevents concurrent syncs)
    ├── Spawn sync_worker.py as background process (stdout/stderr → DEVNULL)
    │   Worker logs to `{library}/.librarian/sync_worker.log`
    │   Return immediately to MCP client
    │
    ▼ (in background worker)
    LibraryManager.get_library("botany")
    │
    ├── Load config.yaml → get chromadb path, collection name
    ├── Create ChonkieBackend(collection_name="botany", db_path=".../chromadb/")
    ├── Create Indexer(manager, backend)
    │
    ▼ Indexer.index_library("botany")
    │
    ├── Load metadata/index.json (existing checksums + document_ids)
    ├── Discover files (._discover_files with .librarianignore)
    │
    ├── First pass: checksum comparison
    │   ├── Unchanged → skip
    │   └── New/changed → add to processing list
    │
    ├── Cleanup phase (single ChromaDB connection):
    │   ├── [DELETE] Files removed from disk → remove chunks + remove from metadata
    │   └── [UPDATE] Files being updated → remove old chunks (metadata entry kept for overwrite)
    │
    ├── Second pass: batch process changed files through backend
    │   ├── SemanticChunker chunks text
    │   ├── Store in per-library ChromaDB with metadata (pure insert)
    │   └── Return chunk info (including document_id)
    │
    ├── Store metadata with document_id for future deletions
    ├── Update status via LibraryStatus
    │
    └── Return: {added: N, updated: M, skipped: K, deleted: D, errors: E}
```

### Full Rebuild (rebuild_library_async)

Same flow as incremental sync, but first clears ChromaDB and metadata:

```
rebuild_library_async(library="botany")
    │
    ├── Clear ChromaDB collection (delete + recreate)
    ├── Clear metadata/index.json
    │
    └── Run full index_library() (all files treated as new)
```

---

## Chunk Cleanup Architecture

The Indexer owns all chunk deletion through a single unified cleanup phase. The backend (`ChonkieBackend`) is a pure insert-only operation — it never queries or deletes chunks.

### Design Principle

All lifecycle decisions belong to the Indexer because it has the complete picture:
- It knows what's on disk (from file discovery)
- It knows what's indexed (from metadata)
- It knows what's changing (from checksums)

The backend only transforms: text → chunks → insert.

### Cleanup Phase

After the first pass (checksum comparison), the Indexer opens a single ChromaDB connection and handles both cleanup scenarios:

| Scenario | Log Prefix | Trigger | Action |
|----------|-----------|---------|--------|
| **File Deletion** | `[DELETE]` | File in metadata, not on disk | Remove all chunks + remove metadata entry |
| **File Update** | `[UPDATE]` | File changed and already in metadata | Remove old chunks (keep metadata entry for overwrite) |

Both scenarios query ChromaDB by the `source` metadata field (absolute file path).

### Sync Flow

```
Indexer First Pass:
  ├── checksum comparison
  └── categorize: new / changed / skipped

Indexer Cleanup Phase:
  ├── [DELETE] files removed from disk
  │   └── collection.get(where={"source": abs_path}) → delete chunks → remove from metadata
  └── [UPDATE] files being updated
      └── collection.get(where={"source": abs_path}) → delete old chunks

Indexer Second Pass → Backend (pure insert):
  ├── extract text from file
  ├── SemanticChunker chunks text
  └── collection.add() → new chunks inserted
```

### Why Centralized?

Previous architecture had deletion split across two components:
- Indexer handled file-deletion-from-disk (queried by `document_id`)
- Backend handled old-chunk-cleanup-during-reindex (queried by `source`)

This caused:
- Inconsistent query strategies (`document_id` vs `source`)
- Two ChromaDB connections for the same sync operation
- Broken `file_deleted` check that read from a hardcoded relative path

Centralizing in the Indexer means:
- One query strategy (`source` for all)
- One ChromaDB connection
- One owner of lifecycle decisions
- Backend is a simple, testable text→chunks→insert pipeline

### Related Bugs (Resolved)

- **BUG-002**: Old chunks not deleted before re-indexing
- **BUG-021**: Files deleted from disk not cleaned up from ChromaDB
- **BUG-022**: Incremental sync reports `updated: 1` but chunk count unchanged

---

## Security Architecture

### Layer 1: Dynamic Library Boundary (CLI Tools)

CLI tools validate paths against registered library roots — not a single SAFE_DIR.

```python
is_library_path("/home/peter/botany/plants/oak.md")     → ✅ ALLOWED
is_library_path("/home/peter/martha-health/records.md")  → ✅ ALLOWED
is_library_path("/home/peter/random-project/file.py")    → ❌ BLOCKED
is_library_path("/home/peter/.ssh/config")               → ❌ BLOCKED
```

Boundary is dynamic — registering a new library automatically extends what the LLM can access.

### Layer 2: Report Write Sandbox (write_document)

Writes go to two locations when a library context is provided:

1. **Global sandbox** — `/home/peter/.librarian/{path}` (always, backward compatible)
2. **Library delivery** — `{library_root}/delivery/{path}` (when `library` parameter is provided)

The library delivery path enables distributed setups: files written to `delivery/` are synced to remote devices by Syncthing. The user finds deliverables in their own vault without interacting with the server directly.

Security constraints on both write paths:
- Path traversal blocked (`..`, `/`, `\`, `.`)
- Critical patterns blocked (`password`, `secret`, `.env`)
- File size and depth limits enforced
- Delivery path validated to stay within `library_root/delivery/`

### Layer 3: Command Whitelisting

```python
ALLOWED = {"ls", "cat", "grep", "find", "head", "tail", "wc", "sort", ...}
BANNED  = {"rm", "chmod", "wget", "curl", "python", "bash", "ssh", ...}
```

### Layer 4: Resource Limits

- Command timeout: 15 seconds
- Output truncation: 8,000 characters
- Max write size: 100KB
- Max document size: 10MB

### Layer 5: .librarianignore

Gitignore-style patterns loaded from `{library_root}/.librarianignore`:
- Security: `.env`, `*.key`, `*.pem`, `credentials.*`
- Development: `venv/`, `node_modules/`, `__pycache__/`
- Databases: `*.sqlite`, `*.db`
- OS: `.DS_Store`, `Thumbs.db`

---

## Network Transport

### Localhost (Default)

The MCP server listens on localhost ports by default:

| Mode | Port | Endpoint |
|------|------|----------|
| LibraryManager | 8889 | `http://localhost:8889/mcp` |
| LibraryUser | 8890 | `http://localhost:8890/mcp` |
| Admin | 8891 | `http://localhost:8891/mcp` |
| Dashboard | 8892 | `http://localhost:8892` |

No ports are exposed to external interfaces. The server binds to `127.0.0.1` only.

### Tailscale Remote Access

The localhost restriction can be extended to include remote clients over a [Tailscale](https://tailscale.com/) tailnet — a mesh VPN that provides encrypted peer-to-peer connections between your devices without opening public ports.

When the MCP server machine and a client device (e.g., a family member's laptop) are members of the same tailnet, the client can substitute `localhost` with the server's Tailscale IPv4 address in the MCP configuration:

```json
{
  "type": "http",
  "url": "http://100.x.y.z:8890/mcp"
}
```

Where `100.x.y.z` is the server's Tailscale address.

**How this works:**
- Tailscale assigns each device a stable `100.x.y.z` address within your private tailnet
- Traffic is encrypted end-to-end using WireGuard
- No firewall ports are opened — connections are brokered through Tailscale's coordination server
- The server sees the connection as coming from a tailnet IP, not the public internet

**Security considerations:**
- Access is limited to devices you have explicitly added to your tailnet
- The current access control is prompt-level (the AI is instructed which tools and libraries to use)
- Server-level authentication and per-library access restrictions are planned for a future release
- For family deployments, prompt-level control is adequate. For multi-user environments, additional auth should be implemented before exposing the server over Tailscale

This deployment pattern is particularly useful for:
- Sharing a medical library with a family member who connects from their own device
- Accessing your libraries from a laptop or another machine on your home network
- Remote consultation scenarios where a specialist or caregiver needs temporary access

### Library Locality

Clients can be remote. Libraries cannot.

Libraries must reside on the same machine as the MCP server. This is a design requirement, not a limitation — the server's relationship with its libraries is deeply local:

- **In-place indexing** walks the actual filesystem directory tree
- **SHA-256 checksums** are computed against local files during sync
- **ChromaDB instances** live inside each library's `.librarian/chromadb/` directory
- **Incremental sync** compares live disk state against stored metadata

The server doesn't merely reference libraries — it operates directly on the filesystem they live in. Making libraries remote would require either a network filesystem layer (NFS, SMB) or a complete architectural redesign, neither of which provides a meaningful benefit over the current topology: one server, local libraries, remote clients.

```
Server + Libraries (same machine)     Clients (anywhere on tailnet)
─────────────────────────────         ──────────────────────────────
┌──────────────────────┐              ┌──────────────────────┐
│ MCP Server           │◀──network───│ Jan (laptop)         │
│ ├── Library A (disk) │              ├──────────────────────┤
│ ├── Library B (disk) │◀──network───│ Jan (sister's Mac)   │
│ └── Library C (disk) │              ├──────────────────────┤
└──────────────────────┘              │ LM Studio (desktop)  │
         │                            └──────────────────────┘
         │  Syncthing (optional)
         │  bidirectional mirror
         ▼
┌──────────────────────┐
│ Remote device        │
│ ├── Library mirror   │  ← user edits here
│ └── delivery/        │  ← MCP reports sync here
└──────────────────────┘
```

---

## Supported File Types

### Indexed (text only)
| Category | Extensions |
|----------|-----------|
| Text | `.md`, `.txt`, `.rst`, `.log` |
| Code | `.py`, `.js`, `.ts`, `.sh`, `.bash`, `.zsh` |
| Config | `.yaml`, `.yml`, `.toml`, `.json` |
| Web | `.html` |
| Data | `.csv`, `.tsv` |

HTML files are converted to Markdown via `html2text` before chunking (links preserved as markdown, images skipped, no line wrapping). Metadata `file_type` stays `.html` so the source format is always traceable.

### Not Indexed (silently skipped)
PDF, DOCX, images, archives, executables. Pre-convert to Markdown before creating a library.

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| MCP Framework | FastMCP | Tool registration and transport |
| Dashboard | FastAPI | Web status page |
| Language | Python 3.13 | Core implementation |
| Vector DB | ChromaDB (per-library) | Semantic search storage |
| Chunking | Chonkie SemanticChunker | Semantic text splitting (all file types) |
| Chunking Embeddings | minishlab/potion-base-32M | Chunk boundary decisions |
| Search Embeddings | ChromaDB default | Similarity vector generation |
| Configuration | YAML | Library configs and registry |
| Change Detection | SHA-256 | Incremental sync |
| HTML Conversion | html2text | HTML → Markdown pre-chunking |

---

## CPU-Optimized Design

The system runs entirely on CPU with no GPU dependency. This is not a compromise — it's the optimal architecture for both models used in the pipeline.

### Why No GPU Is Needed

Two embedding operations happen during indexing and search. Neither benefits from a GPU:

**1. Chunking Model: `minishlab/potion-base-32M` (Model2Vec)**

This is a **static embedding model** — a lookup table mapping tokens to precomputed vectors, not a neural network. There is no forward pass, no transformer layers, no matrix multiplication. Copying data to the GPU and back would take longer than the CPU lookup. The `sentence-transformers` `StaticEmbedding` docstring confirms this explicitly:

> *Due to the extremely efficient nature of this module architecture, the overhead for moving inputs to the GPU can be larger than the actual computation time. Therefore, consider using a CPU device for inference and training.*

The model loads once in `ChonkieBackend.__init__()` and stays in memory as a `Model2VecEmbeddings` object for the lifetime of the sync worker process.

**2. Search Embedding Model: `BAAI/bge-small-en-v1.5` (ChromaDB default)**

ChromaDB generates similarity vectors automatically on `collection.add()` and `collection.query()` using its default `sentence-transformers` embedding function, which runs on CPU. The small variant (33M parameters) handles batch embedding during indexing without GPU acceleration.

### Implications

| Aspect | Detail |
|--------|--------|
| **Hardware** | Runs on any x86_64 machine with 8GB RAM and an SSD |
| **Latency** | Sync of a 69-document library completes in ~20 seconds |
| **Deployment** | No CUDA, no driver dependencies, no GPU contention |
| **Cost** | Standard PC hardware, no GPU-tier cloud instances |

### What Would Need a GPU

Only a full transformer-based embedding model (e.g., `all-MiniLM-L6-v2`, `bge-large-en-v1.5`) used as the **search embedding** would meaningfully benefit from GPU acceleration — and even then, only for very large libraries (100,000+ chunks). The current static chunking model + small search embedding combination is CPU-native by design.

---

## File Map

### Core Components
```
mcp_server/
├── __init__.py               # Package init
├── librarian_mcp.py          # Server entry point
├── config/
│   ├── __init__.py           # Package init
│   ├── settings.py           # System settings (LIBRARIAN_HOME, BACKEND, etc.)
│   ├── config_loader.py      # YAML configuration loading
│   ├── server_mode.py        # Tool set definitions per mode
│   └── librarian_prompt.py   # System prompt for LLM
├── core/
│   ├── __init__.py           # Package init
│   ├── library_manager.py    # Library registry and lifecycle
│   ├── indexer.py            # In-place file indexing
│   ├── chromadb_orchestrator.py  # Per-library ChromaDB management
│   ├── library_status.py     # Atomic status updates
│   └── ignore_patterns.py   # .librarianignore matching
├── backend/
│   ├── __init__.py           # Package init
│   ├── base.py               # Abstract backend interface
│   ├── chroma_backend.py     # ChromaDB storage (per-library)
│   ├── chonkie_backend.py    # Semantic chunking
│   └── factory.py            # Backend creation
├── tools/
│   ├── __init__.py           # Package init
│   ├── library_tools.py      # All MCP tools (library + CLI + admin)
│   └── keyword_search.py     # Text matching for keyword search
└── ai_layer/
    └── __init__.py           # Unused AI abstraction (dead code, still on disk)

### Dashboard
```
dashboard/
├── app.py                  # FastAPI application (API + serve HTML)
└── static/
    ├── index.html           # Dashboard page
    └── style.css            # Styling
```

### Scripts
```
scripts/
├── sync_worker.py            # Background indexing process
└── (various utility scripts)
```

### Startup
```
start_multi_mode.sh           # Start all 3 server modes
stop_multi_mode.sh            # Stop all servers
```

---

## Data Locations

| What | Where | Purpose |
|------|-------|---------|
| Library registry | `<project>/global_control/.library_control/libraries.yaml` | Lists all registered libraries |
| Global config | `<project>/global_control/.library_control/config.yaml` | System-wide configuration |
| Library config | `{library_root}/.librarian/config.yaml` | Per-library configuration |
| Library metadata | `{library_root}/.librarian/metadata/index.json` | File checksums, document IDs |
| Library ChromaDB | `{library_root}/.librarian/chromadb/` | Per-library vector database |
| Library status | `{library_root}/.librarian/status/` | Sync status files |
| Library delivery | `{library_root}/delivery/` | Per-library report output (synced to remote devices via Syncthing) |
| Library ignore | `{library_root}/.librarianignore` | Files excluded from indexing (auto-created by `add_library`) |
| Syncthing ignore | `{library_root}/.stignore` | Files excluded from Syncthing sync (auto-created by `add_library`) |
| Reports (global) | `/home/peter/.librarian/` | Central report write location |

---

## Key Differences from Previous Architecture

| Aspect           | Previous (Shadow)                              | Blue Sky (Current)                                           |
| ---------------- | ---------------------------------------------- | ------------------------------------------------------------ |
| Document storage | Shadow copies in `/home/user/library_shadows/` | In-place, no copies                                          |
| ChromaDB         | Single global instance                         | Per-library instances                                        |
| CLI security     | Single `SAFE_DIR` pointing to shadow root      | Dynamic validation against library registry                  |
| Report writes    | `{SAFE_DIR}/.librarian/{path}`                 | `/home/user/.librarian/{path}` + per-library `delivery/`     |
| Collection name  | `librarian_documents` (global)                 | Library name (per-library)                                   |
| Shadow Manager   | Required                                       | Deleted                                                      |
| Document Manager | Required                                       | Deleted (BUG-006)                                            |
| Metadata Store   | Global store                                   | Deleted (per-library index.json)                             |
| Binary support   | Filtered by Shadow Manager                     | None — text only                                             |
| Chunking         | SemanticChunker (all types)                    | SemanticChunker (all types, file-type-aware planned for 1.1) |
