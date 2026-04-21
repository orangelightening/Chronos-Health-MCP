# Librarian MCP — Installation & Setup Guide

**Last Updated:** 2026-04-20
**Audience:** Anyone setting up the Librarian MCP system

---

## Table of Contents

1. [Requirements](#requirements)
2. [Server Installation](#server-installation)
3. [Starting the Server](#starting-the-server)
4. [MCP Client Configuration](#mcp-client-configuration)
5. [Getting the Demo Libraries Running](#getting-the-demo-libraries-running)
6. [Creating Your First Library](#creating-your-first-library)
7. [Managing Libraries](#managing-libraries)
8. [Directory Structure](#directory-structure)
9. [Troubleshooting](#troubleshooting)

---

## Requirements

| Requirement | Detail |
|------------|--------|
| **Python** | 3.13 or later |
| **OS** | Linux (Ubuntu 22.04+, Debian 12+). macOS and WSL2 may work but are untested |
| **RAM** | 8 GB minimum |
| **Disk** | ~2 GB for models + space for your libraries' ChromaDB indexes |
| **GPU** | **Not required.** The system is CPU-optimized by design |
| **Network** | Localhost only. No internet needed after first model download |

### Why No GPU?

Both models in the pipeline are CPU-native:

- **Chunking model** (`minishlab/potion-base-32M`) — a static lookup table (Model2Vec), not a neural network. GPU overhead would be slower than CPU.
- **Search embedding model** (`BAAI/bge-small-en-v1.5`, 33M params) — ChromaDB's default, runs on CPU.

No CUDA, no driver dependencies, no GPU-tier hardware needed.

---

## Server Installation

### 1. Clone and Set Up Virtual Environment

```bash
git clone https://github.com/orangelightening/Chronos-Health-MCP.git
cd Chronos-Health-MCP
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

This installs all dependencies including:
- **FastMCP** — MCP framework for tool registration and HTTP transport
- **ChromaDB** — Per-library vector database
- **Chonkie** — Semantic chunking engine
- **model2vec** — Static embedding model loader
- **html2text** — HTML → Markdown conversion for `.html` file indexing

### 2. First Model Download

The first time you start the server, the chunking model (`minishlab/potion-base-32M`, ~129 MB) will download from HuggingFace Hub and cache at `~/.cache/huggingface/hub/`. Subsequent starts use the cached copy.

### 3. Report Directory

The server creates `~/.librarian/` on first startup. This is the **central report sandbox** — all reports written by the AI (via `write_document`) go here. This directory is created automatically; no setup needed.

```
~/.librarian/                  # Central report sandbox
├── analysis-report.md         # Example report written by AI
├── findings-2026-04-13.md     # Another report
└── ...
```

---

## Starting the Server

### Start All Three Modes

```bash
./start_multi_mode.sh
```

This starts three server processes:

| Mode | Default Port | Tools | Purpose |
|------|-------------|-------|---------|
| **LibraryUser** | 8890 | 14 | End users, search, browse, reports |
| **LibraryManager** | 8889 | 18 | Library creation, sync, rebuild |
| **Admin** | 8891 | All | Full system control including admin commands |

The script performs a health check and reports status for each mode.

### Custom Ports

```bash
./start_multi_mode.sh --librarymanager-port 9001 --libraryuser-port 9002 --admin-port 9003
```

### Stop All Servers

```bash
./stop_multi_mode.sh
```

### Logs

Server logs are written to `/tmp/librarian-*.log`:
```
/tmp/librarian-LibraryManager.log
/tmp/librarian-LibraryUser.log
/tmp/librarian-Admin.log
```

Per-library sync/rebuild logs are at `{library_root}/.librarian/sync_worker.log`.

---

## MCP Client Configuration

Your MCP client needs to connect to one of the three Librarian server endpoints. Choose the mode that matches your use case:

| If You Want...                             | Connect To                                   |
| ------------------------------------------ | -------------------------------------------- |
| End users searching and reading documents  | `http://localhost:8890/mcp` (LibraryUser)    |
| Managing libraries (create, sync, rebuild) | `http://localhost:8889/mcp` (LibraryManager) |
| Full system administration                 | `http://localhost:8891/mcp` (Admin)          |

---

### Jan.ai Configuration

Jan is a local AI client with built-in MCP support. Here's how to connect it to the Librarian.

#### Step 1: Install Jan

Download from [jan.ai](https://jan.ai/) and install.

#### Step 2: Add MCP Servers

Go to **Settings → MCP Servers** and add the Librarian endpoint(s) you need. Each endpoint is a separate MCP server entry.

For HTTP-type servers, the configuration JSON looks like this:

```json
{
  "active": true,
  "args": [],
  "command": "",
  "env": {},
  "type": "http",
  "url": "http://localhost:8890/mcp"
}
```

Repeat for each endpoint you want to connect:

| Server Name | URL |
|-------------|-----|
| Librarian (User) | `http://localhost:8890/mcp` |
| Librarian (Manager) | `http://localhost:8889/mcp` |
| Librarian (Admin) | `http://localhost:8891/mcp` |

If the Librarian server is running, the status indicator will turn **green** once the connection succeeds.

#### Step 3: Create a Librarian Assistant

1. Go to **Settings → Assistants** and create a new assistant
2. Set the system prompt using the appropriate prompt file from the project:
   - **`system_prompt_librarian.md`** — for search, analysis, and report writing
   - **`system_prompt_librarian+coder.md`** — for coding tasks (also works as a coding assistant)
3. Save the assistant

#### Step 4: Set Up a Chat Project

1. Go to **New Project** and create a chat (e.g., "Library Chat")
2. In the project configuration, select the assistant you just created
3. Go to the **Hub** and download a model suitable for your tasks (see model recommendations below)
4. Start a chat inside the project

#### Step 5: Verify the Connection

Open the **Tools** icon in the chat to confirm the Librarian tools are available. Then test with:

> "List the available libraries."

You should see your registered libraries listed. If so, you're connected and ready to go.

#### Recommended Model Sizes

| Use Case | Model Size | Notes |
|----------|-----------|-------|
| Search and reading | 9B+ | LibraryUser mode (14 tools) works well with smaller models |
| Library management | 9B+ | LibraryManager mode needs a model that can select from 18 tools |
| Coding assistance | 14B+ | Larger models handle code analysis and the Librarian+Coder prompt better |

#### Optional: Add the Filesystem MCP Server

For coding workflows, add Jan's built-in **Filesystem MCP** server alongside the Librarian. This gives the AI better file write and edit capabilities. Use with the Librarian (Admin) endpoint and the `system_prompt_librarian+coder.md` prompt for the best coding experience.

---

### Other MCP Clients

The Librarian uses standard HTTP MCP transport. Any MCP-compatible client should work by pointing it at one of the three endpoint URLs listed in the table above. This has been tested with lmstudio.
**See documents/clients for information on more clients and different configurations including remote access**
---

## Getting the Demo Libraries Running

The system ships with no libraries registered. Two sample libraries are included in the repo for you to explore:

1. **The project source itself** — all the code, documentation, and configuration you just cloned
2. **Sample medical library** — a small demonstration library at `examples/sample-library/`

To register them, ask your AI:

> "Add library `/path/to/your/librarian-mcp` called librarian-mcp."

> "Add library `/path/to/your/librarian-mcp/examples/sample-library` called sample-library."

Replace `/path/to/your/` with the actual path where you cloned the repo. Then verify:

> "List libraries."

> "Get library stats for both libraries."

You should see both libraries with documents and chunks indexed. You're ready to explore.

### What `add_library` Does

The `add_library` command:
1. Creates a `.librarian/` directory inside the target folder (ChromaDB, metadata, config)
2. Creates a `.librarianignore` file with sensible defaults (`.env`, `*.key`, `venv/`, etc.)
3. Registers the library in the system registry
4. Triggers an initial sync that indexes all supported files

Source documents are never modified or copied. The `.librarian/` directory holds only index data.

## Creating Your First Library

Once your client is connected, ask your AI to add a library:

> add_library  `/path/to/your/documents`  called my-library."

The AI will:
1. Create the `.librarian/` directory structure inside your document folder
2. Index all supported files (`.md`, `.txt`, `.py`, `.html`, etc.)
3. Store chunks in a per-library ChromaDB instance

Then search immediately:

> "Search my-library library for information about [topic]."

No configuration files to edit, no databases to set up.

---

## Managing Libraries

### Deleting Libraries

If you no longer need a library, ask your AI to delete it:

> "Delete my-library library."

This removes the library from the registry and deletes its `.librarian/` directory containing ChromaDB, metadata, and status files. **Source documents remain untouched.**

### Phantom (Broken) Libraries

You may encounter libraries marked as **BROKEN** when running `list_libraries()`. These are "phantom libraries" — libraries registered in the system but whose paths no longer exist.

**Why This Happens:**

This typically occurs when you:
- Move or rename a library directory without updating the library registry
- Delete a library directory manually without using the delete_library tool
- Copy a library's `libraries.yaml` configuration from another machine

The system detects these broken paths and prevents operations on them to avoid confusing errors.

**How to Detect Broken Libraries:**

Run `list_libraries()` and look for the ⚠️ indicator:

```
📚 **Registered Libraries** (5) — 2 valid, 3 broken

[1] ⚠️ katherine-health (BROKEN)
  Path: /home/peter/health-libraries/katherine-health
  Status: Library path does not exist
  Description: Katherine's medical records
  Registered: 2026-04-16T19:03:12.927961
```

**What Happens with Broken Libraries:**

- **Cannot search:** Search operations return clear error with broken path
- **Cannot sync:** Sync operations return clear error with broken path
- **Cannot view stats:** Stats operations return clear error with broken path
- **Can be deleted:** You can delete broken libraries to clean up the registry

**How to Fix Broken Libraries:**

You have two options:

**Option 1: Delete the broken library entry**

If you've moved or deleted the library and don't need it:

> "Delete katherine-health library."

This removes the library from the registry. Since the path doesn't exist, no `.librarian/` directory is deleted — only the registry entry is removed.

**Option 2: Update the library path**

If you've moved the library to a new location and want to keep it:

1. Edit `global_control/.library_control/libraries.yaml`
2. Find the library entry with the broken path
3. Update the `path` field to the new location:
   ```yaml
   libraries:
   - description: Katherine's medical records
     name: katherine-health
     path: /new/path/to/katherine-health  # Update this
     registered_at: '2026-04-16T19:03:12.927961'
   ```
4. Restart the servers (stop and start with `stop_multi_mode.sh` / `start_multi_mode.sh`)

The library will now be detected as valid and operations will work normally.

### Supported File Types

**Indexed:** `.md`, `.txt`, `.rst`, `.py`, `.js`, `.ts`, `.sh`, `.json`, `.yaml`, `.yml`, `.toml`, `.html`, `.css`, `.csv`, `.tsv`

**Not indexed:** PDF, DOCX, images, archives, binaries. Pre-convert to Markdown before creating a library.

### Excluding Files

Create a `.librarianignore` file in your library root (gitignore-style patterns):

```
# Exclude sensitive files
.env
*.key
credentials.*

# Exclude development artifacts
node_modules/
__pycache__/
*.pyc

# Exclude databases
*.sqlite
*.db
```

---

## Directory Structure

After installation and library creation, the directory layout looks like this:

```
librarian-mcp/                     # Server installation
├── mcp_server/                    # Source code
├── scripts/
│   └── sync_worker.py             # Background indexing process
├── start_multi_mode.sh            # Start all 3 server modes
├── stop_multi_mode.sh             # Stop all servers
└── requirements.txt               # Python dependencies

~/.cache/huggingface/hub/          # Cached models (first download ~129 MB)
~/.librarian/                      # Central report sandbox (auto-created)

your-library/                      # Your documents (wherever they live)
└── .librarian/                    # Created on registration (auto-created)
    ├── config.yaml                # Library configuration
    ├── chromadb/                  # Per-library vector database
    ├── metadata/
    │   └── index.json             # File checksums and document IDs
    ├── status/                    # Sync status files
    └── sync_worker.log            # Last sync/rebuild log
```

Key points:
- **Libraries live where your documents are.** No copying, no shadow directories.
- **Each library has its own ChromaDB.** Completely isolated from other libraries.
- **The report sandbox is central.** All AI-written reports go to `~/.librarian/`, separate from your libraries.

---

## Troubleshooting

### Library Operations Fail with "Broken Path" Error

If you see errors like:
```
❌ Library 'my-library' has a broken path: /old/path/to/my-library

This library cannot be searched. Please fix the path in
global_control/.library_control/libraries.yaml or delete the
library using delete_library().
```

See the [Managing Libraries](#managing-libraries) section above for detailed instructions on fixing or deleting broken (phantom) libraries.

### Server Won't Start

**"No virtual environment" error:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Port already in use:**
```bash
# Check what's using the port
ss -tlnp | grep 8890
# Stop existing servers
./stop_multi_mode.sh
```

### Model Download Issues

If the first startup fails to download the model:
1. Check internet connectivity (HuggingFace Hub)
2. The model caches at `~/.cache/huggingface/hub/models--minishlab--potion-base-32M/`
3. Once cached, no internet is needed

### Sync Seems Slow

First sync of a large library will take time (proportional to document count). Subsequent syncs use SHA-256 checksums and only process changed files — typically seconds.

### Search Returns No Results

Run a full rebuild to re-index from scratch:
```
> "Rebuild the my-library library index."
```

This clears ChromaDB and re-indexes all files. Use for corrupted indexes or after model changes.

---

## What's Next?

- Read [README.md](README.md) for features and architecture overview
- Read [ARCHITECTURE_v2.md](ARCHITECTURE_v2.md) for complete technical documentation
- Read [SYSTEM_REFERENCE.html](SYSTEM_REFERENCE.html) for the visual system reference
