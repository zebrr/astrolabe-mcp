# spec_config — Configuration Loading

Status: READY

## Overview

Loads `config.json` and `doc_types.yaml`, returning validated `AppConfig` and document type definitions.

## Public API

### `load_config(config_path: Path) -> AppConfig`

Load and validate `config.json`.

- `config_path`: absolute path to config.json
- `index_dir` is resolved relative to the config file's parent directory
- Non-existent project paths are kept (skipped at scan time, not load time)
- Raises `FileNotFoundError` if config file missing
- Raises `pydantic.ValidationError` if config structure invalid

### `load_doc_types_full(doc_types_path: Path) -> dict[str, dict[str, Any]]`

Load `doc_types.yaml` and return full structure for each document type.

- `doc_types_path`: absolute path to doc_types.yaml
- Returns `{}` if file is missing (soft dependency — doc_types are optional)
- Raises `yaml.YAMLError` if file exists but is malformed
- Each value is a dict with keys: `description` (str), `examples` (list[str], optional)
- Preserves all fields from yaml as-is (future-proof)

### `load_doc_types(doc_types_path: Path) -> dict[str, str]`

Convenience wrapper. Returns flat mapping of `type_name → description`.

- Delegates to `load_doc_types_full()`, extracts description from each entry
- Returns `{}` if file is missing

## Dependencies

- `astrolabe.models.AppConfig`
- `pyyaml`
- `json` (stdlib)
- `pathlib` (stdlib)

## Usage Examples

```python
from pathlib import Path
from astrolabe.config import load_config, load_doc_types, load_doc_types_full

config = load_config(Path("/path/to/config.json"))

# Full structure (for get_doc_types tool / skill classification)
full = load_doc_types_full(Path("/path/to/doc_types.yaml"))
# full == {"instruction": {"description": "Project instruction...", "examples": ["CLAUDE.md"]}, ...}

# Flat mapping (for get_cosmos descriptions, backward compat)
flat = load_doc_types(Path("/path/to/doc_types.yaml"))
# flat == {"instruction": "Project instruction...", "reference": "Reference material..."}
```
