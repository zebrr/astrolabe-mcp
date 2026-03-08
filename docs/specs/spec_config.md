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

### `load_doc_types(doc_types_path: Path) -> dict[str, str]`

Load `doc_types.yaml` and return a flat mapping of `type_name → description`.

- `doc_types_path`: absolute path to doc_types.yaml
- Returns `{}` if file is missing (soft dependency — doc_types are optional)
- Raises `yaml.YAMLError` if file exists but is malformed

## Dependencies

- `astrolabe.models.AppConfig`
- `pyyaml`
- `json` (stdlib)
- `pathlib` (stdlib)

## Usage Examples

```python
from pathlib import Path
from astrolabe.config import load_config, load_doc_types

config = load_config(Path("/path/to/config.json"))
doc_types = load_doc_types(Path("/path/to/doc_types.yaml"))
# doc_types == {"instruction": "Project instruction...", "reference": "Reference material..."}
```
