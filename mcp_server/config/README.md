# Configuration System

The Librarian MCP server uses a hierarchical YAML-based configuration system with environment variable override support.

## Configuration Files

### Global Configuration

**Location:** `<project>/global_control/.library_control/config.yaml`

Global system settings including:
- Backend configuration (Chonkie API)
- Chunking strategies (file-type specific)
- Allowed file types
- Security settings
- Performance tuning
- Async operation settings

### Library Registry

**Location:** `<project>/global_control/.library_control/libraries.yaml`

Registry of all managed libraries with:
- Library names and paths
- Registration timestamps
- Status information
- Statistics (document count, chunk count, etc.)

### Library-Specific Configuration

**Location:** `{library_path}/.librarian/config.yaml`

Per-library settings for:
- Indexing configuration
- File type patterns
- ChromaDB settings
- Status tracking

## Configuration Hierarchy

Settings are loaded in priority order (highest first):

1. **Environment Variables** - `LIBRARIAN_*` variables override everything
2. **Library Config** - `.librarian/config.yaml` for library-specific settings
3. **Global Config** - `config.yaml` for system-wide defaults
4. **Code Defaults** - Hardcoded fallbacks in Python code

## Environment Variables

Format: `LIBRARIAN_SECTION_KEY`

Examples:
```bash
# Backend selection
export LIBRARIAN_BACKEND=chonkie
export LIBRARIAN_CHONKIE_URL=http://localhost:8000

# Chunking
export LIBRARIAN_CHUNK_SIZE=1000

# Paths
export LIBRARIAN_REGISTRY_PATH=/custom/path/libraries.yaml

# Security
export LIBRARIAN_MAX_OUTPUT_CHARS=8000
```

## Configuration Loader API

```python
from mcp_server.config.config_loader import (
    load_global_config,
    load_library_config,
    load_libraries_registry,
    get_setting,
    save_library_config,
    save_libraries_registry
)

# Load global configuration
config = load_global_config()
backend_type = get_setting(config, 'backend', 'type', 'chonkie')

# Load library configuration
library_config = load_library_config(Path("/home/peter/botany"))

# Load libraries registry
registry = load_libraries_registry()
libraries = registry.get('libraries', [])

# Save configuration
save_library_config(library_path, new_config)
save_libraries_registry(updated_registry)
```

## File Types

Default allowed file extensions for indexing:

- **Text:** `.md`, `.txt`, `.rst`, `.log`
- **Shell:** `.sh`, `.bash`, `.zsh`
- **Code:** `.py`, `.js`, `.ts`, `.json`
- **Config:** `.yaml`, `.yml`, `.toml`
- **Web:** `.html`, `.css`, `.scss`
- **Data:** `.csv`, `.tsv`

## Chunking Strategies

### Markdown Files
- Processor: `markdown`
- Chunker: `semantic`
- Chunk size: 1000 tokens

### Code Files (.py, .js, .ts, .sh, .bash, .zsh)
- Processor: `text`
- Chunker: `code`
- Chunk size: 1000 tokens

### Other Text Files
- Processor: `text`
- Chunker: `semantic`
- Chunk size: 1000 tokens

## Atomic Write Pattern

All configuration writes use atomic file operations:

1. Write to temporary file (`.yaml.tmp`)
2. Flush to disk
3. Rename over original file

This prevents corruption if the process crashes during writes.

## Migration from JSON to YAML

The Blue Sky architecture migrated from JSON to YAML for:

- **Human readability** - Easier to edit manually
- **Comments** - YAML supports inline documentation
- **Hierarchy** - Better nested structure support
- **Industry standard** - Widely used in DevOps/tools

Legacy JSON configurations are automatically migrated on first load.

## Default Values

The system includes sensible defaults for all settings. Custom configuration is optional.

**Minimum required configuration:**
- None (system works with defaults)

**Recommended customizations:**
- Backend URL (if using remote Chonkie API)
- File type patterns (for specific use cases)
- Chunk size (for domain-specific tuning)

## Security

- Configuration files in project directory (`global_control/.library_control/`)
- No sensitive data stored in config (use environment variables)
- File permissions set appropriately (0600 for files, 0700 for directories)
- Path validation prevents directory traversal attacks

## Troubleshooting

### Config not loading?
```bash
# Check file exists
ls -la global_control/.library_control/config.yaml

# Check YAML syntax
python3 -c "import yaml; yaml.safe_load(open('global_control/.library_control/config.yaml'))"
```

### Environment variables not working?
```bash
# Check variable is set
echo $LIBRARIAN_BACKEND

# Must be uppercase with LIBRARIAN_ prefix
export LIBRARIAN_BACKEND=chonkie
```

### Registry corrupted?
```bash
# The system will auto-recover with empty registry
# Or manually restore from backup
cp global_control/.library_control/libraries.yaml.backup \
   global_control/.library_control/libraries.yaml
```
