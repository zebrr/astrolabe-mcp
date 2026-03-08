"""Configuration loading for astrolabe-mcp."""

import json
from pathlib import Path

import yaml

from astrolabe.models import AppConfig


def load_config(config_path: Path) -> AppConfig:
    """Load and validate config.json.

    Args:
        config_path: Absolute path to config.json.

    Returns:
        Validated AppConfig.

    Raises:
        FileNotFoundError: If config file does not exist.
        pydantic.ValidationError: If config structure is invalid.
    """
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    config = AppConfig.model_validate(raw)

    # Resolve index_dir relative to config file directory
    if not config.index_dir.is_absolute():
        config.index_dir = config_path.parent / config.index_dir

    return config


def load_doc_types(doc_types_path: Path) -> dict[str, str]:
    """Load doc_types.yaml and return type_name → description mapping.

    Args:
        doc_types_path: Absolute path to doc_types.yaml.

    Returns:
        Dict mapping type names to descriptions. Empty dict if file missing.

    Raises:
        yaml.YAMLError: If file exists but is malformed YAML.
    """
    if not doc_types_path.exists():
        return {}

    raw = yaml.safe_load(doc_types_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "document_types" not in raw:
        return {}

    result: dict[str, str] = {}
    for type_name, type_def in raw["document_types"].items():
        if isinstance(type_def, dict) and "description" in type_def:
            result[type_name] = type_def["description"].strip()
    return result
