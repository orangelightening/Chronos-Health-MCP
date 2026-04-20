# SPDX-License-Identifier: MIT

"""
Configuration Loader for Librarian MCP Server.

This module provides utilities for loading configuration from YAML files
with environment variable override support.

Configuration hierarchy (highest priority first):
1. Environment variables (LIBRARIAN_*)
2. Library-specific .librarian/config.yaml
3. Global .library_control/config.yaml
4. Default values in code

Usage:
    from mcp_server.config.config_loader import load_global_config, load_library_config

    # Load global configuration
    global_config = load_global_config()

    # Load library-specific configuration
    library_config = load_library_config("/home/peter/botany")
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


# Default paths
DEFAULT_CONTROL_DIR = Path(__file__).parent.parent.parent / "global_control" / ".library_control"
DEFAULT_GLOBAL_CONFIG = DEFAULT_CONTROL_DIR / "config.yaml"
DEFAULT_LIBRARIES_YAML = DEFAULT_CONTROL_DIR / "libraries.yaml"


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """
    Load YAML file with error handling.

    Args:
        file_path: Path to YAML file

    Returns:
        Dictionary with YAML contents (empty if file doesn't exist)

    Raises:
        yaml.YAMLError: If YAML parsing fails
        IOError: If file read fails
    """
    if not file_path.exists():
        return {}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except (yaml.YAMLError, IOError) as e:
        print(f"Warning: Could not load {file_path}: {e}")
        return {}


def override_with_env(config: Dict[str, Any], env_prefix: str = "LIBRARIAN_") -> Dict[str, Any]:
    """
    Override configuration values with environment variables.

    Environment variable format: LIBRARIAN_SECTION_KEY
    Example: LIBRARIAN_BACKEND_TYPE=chonkie

    Args:
        config: Configuration dictionary
        env_prefix: Prefix for environment variables

    Returns:
        Configuration dictionary with overrides applied
    """
    result = config.copy()

    for key, value in os.environ.items():
        if not key.startswith(env_prefix):
            continue

        # Remove prefix and convert to lowercase
        config_key = key[len(env_prefix):].lower()

        # Handle nested keys (e.g., BACKEND_TYPE -> backend.type)
        parts = config_key.split('_')

        if len(parts) == 1:
            # Top-level key
            result[parts[0]] = value
        elif len(parts) == 2:
            # Section.key format
            section, key = parts
            if section not in result:
                result[section] = {}
            result[section][key] = value
        else:
            # Deeper nesting - skip for now
            continue

    return result


def load_global_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load global configuration from config.yaml.

    Args:
        config_path: Path to config.yaml (default: <project>/global_control/.library_control/config.yaml)

    Returns:
        Global configuration dictionary with environment overrides

    Example:
        config = load_global_config()
        backend_type = config.get('backend', {}).get('type', 'chonkie')
    """
    if config_path is None:
        config_path = DEFAULT_GLOBAL_CONFIG

    # Load YAML
    config = load_yaml(config_path)

    # Apply environment variable overrides
    config = override_with_env(config)

    return config


def load_library_config(library_path: Path) -> Dict[str, Any]:
    """
    Load library-specific configuration from .librarian/config.yaml.

    Args:
        library_path: Path to library root

    Returns:
        Library configuration dictionary

    Example:
        config = load_library_config(Path("/home/peter/botany"))
        chunk_size = config.get('indexing', {}).get('chunk_size', 1000)
    """
    config_file = Path(library_path) / '.librarian' / 'config.yaml'

    # Load YAML
    config = load_yaml(config_file)

    # No environment overrides for library-specific config
    return config


def load_libraries_registry(registry_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load libraries registry from libraries.yaml.

    Args:
        registry_path: Path to libraries.yaml (default: <project>/global_control/.library_control/libraries.yaml)

    Returns:
        Libraries registry dictionary

    Example:
        registry = load_libraries_registry()
        libraries = registry.get('libraries', [])
    """
    if registry_path is None:
        registry_path = DEFAULT_LIBRARIES_YAML

    # Load YAML
    registry = load_yaml(registry_path)

    return registry


def get_setting(
    config: Dict[str, Any],
    section: str,
    key: str,
    default: Any = None
) -> Any:
    """
    Get configuration value with fallback to default.

    Args:
        config: Configuration dictionary
        section: Section name (e.g., 'backend', 'chunking')
        key: Key within section
        default: Default value if key not found

    Returns:
        Configuration value or default

    Example:
        config = load_global_config()
        backend_type = get_setting(config, 'backend', 'type', 'chonkie')
    """
    try:
        return config.get(section, {}).get(key, default)
    except (AttributeError, TypeError):
        return default


def save_library_config(library_path: Path, config: Dict[str, Any]) -> None:
    """
    Save library configuration to .librarian/config.yaml.

    Args:
        library_path: Path to library root
        config: Configuration dictionary to save

    Uses atomic write pattern (temp file + rename) to prevent corruption.

    Raises:
        IOError: If write fails
        yaml.YAMLError: If YAML serialization fails
    """
    config_dir = Path(library_path) / '.librarian'
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / 'config.yaml'

    # Atomic write
    temp_file = config_file.with_suffix('.yaml.tmp')

    with open(temp_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    temp_file.replace(config_file)


def save_libraries_registry(registry: Dict[str, Any], registry_path: Optional[Path] = None) -> None:
    """
    Save libraries registry to libraries.yaml.

    Args:
        registry: Registry dictionary to save
        registry_path: Path to libraries.yaml (default: <project>/global_control/.library_control/libraries.yaml)

    Uses atomic write pattern (temp file + rename) to prevent corruption.

    Raises:
        IOError: If write fails
        yaml.YAMLError: If YAML serialization fails
    """
    if registry_path is None:
        registry_path = DEFAULT_LIBRARIES_YAML

    # Ensure directory exists
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write
    temp_file = registry_path.with_suffix('.yaml.tmp')

    with open(temp_file, 'w', encoding='utf-8') as f:
        yaml.dump(registry, f, default_flow_style=False, sort_keys=False)

    temp_file.replace(registry_path)
