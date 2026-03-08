# spec_models — Data Models

Status: READY

## Overview

Pydantic models defining all data contracts for astrolabe-mcp: configuration, document index, and tool responses.

## Models

### AppConfig

Application configuration loaded from `config.json`.

```python
class AppConfig(BaseModel):
    projects: dict[str, Path]          # name → absolute path
    index_dir: Path                    # directory for index files (relative to config dir)
    storage: Literal["json", "sqlite"] = "json"  # storage backend
    index_extensions: list[str]        # e.g. [".md", ".yaml"]
    ignore_dirs: list[str]             # directory names to skip
    ignore_files: list[str]            # glob patterns for files to skip
    max_file_size_kb: int              # max file size for full read (without section/range)
```

- `projects`: keys are project IDs used in doc_id, values are absolute paths
- Non-existent project paths are kept in config but skipped at scan time (not at load time)
- `index_dir`: resolved relative to config file directory. Server places `.doc-index.json` or `.doc-index.db` inside.
- `storage`: `"json"` (default) uses `.doc-index.json`, `"sqlite"` uses `.doc-index.db`

### DocCard

Single document in the index. Combines file metadata with agent-enriched fields.

```python
class DocCard(BaseModel):
    project: str
    filename: str                      # basename only
    rel_path: str                      # POSIX relative path from project root
    size: int                          # bytes
    modified: datetime                 # file mtime from filesystem
    content_hash: str                  # MD5 hex digest

    # Enrichment fields (null until agent fills them)
    type: str | None = None
    headings: list[str] | None = None
    summary: str | None = None
    keywords: list[str] | None = None
    enriched_at: datetime | None = None
```

Computed properties:
- `doc_id: str` — `"{project}::{rel_path}"`
- `is_stale: bool` — `enriched_at is not None and modified > enriched_at`
- `is_empty: bool` — `enriched_at is None`

### IndexData

Top-level index structure stored in `.doc-index.json`.

```python
class IndexData(BaseModel):
    version: str = __version__         # from astrolabe.__version__ (pyproject.toml)
    indexed_at: datetime               # last full reindex timestamp
    documents: dict[str, DocCard]      # doc_id → DocCard
```

- Keys are doc_id strings (`project::rel_path`)
- Serialized with `json.dumps(ensure_ascii=False, indent=2)`

### ProjectSummary

Per-project stats for `get_cosmos()` response.

```python
class ProjectSummary(BaseModel):
    id: str
    doc_count: int
    enriched_count: int
    last_indexed: datetime
```

### TypeSummary

Per-type stats for `get_cosmos()` response.

```python
class TypeSummary(BaseModel):
    type: str
    description: str
    count: int
```

### CosmosResponse

Response for `get_cosmos()` tool.

```python
class CosmosResponse(BaseModel):
    server_version: str
    indexed_at: datetime
    total_documents: int
    enriched_documents: int
    stale_documents: int
    empty_documents: int
    desync_documents: int = 0    # files missing on disk or enriched_at > modified
    projects: list[ProjectSummary]
    document_types: list[TypeSummary]
```

### SearchResult

Single result from `search_docs()`.

```python
class SearchResult(BaseModel):
    doc_id: str
    project: str
    type: str | None
    filename: str
    summary: str | None
    keywords: list[str] | None
    relevance: float
```

## Dependencies

- `pydantic >= 2.0`
- `datetime` (stdlib)
- `pathlib` (stdlib)

## Usage Examples

```python
from astrolabe.models import AppConfig, DocCard, IndexData

# Load config
config = AppConfig.model_validate(json.loads(config_path.read_text()))

# Create a doc card
card = DocCard(
    project="neyra",
    filename="README.md",
    rel_path="README.md",
    size=1200,
    modified=datetime(2026, 3, 6),
    content_hash="abc123",
)
assert card.doc_id == "neyra::README.md"
assert card.is_empty is True

# Enrich
card.type = "project_doc"
card.summary = "Main project readme"
card.enriched_at = datetime.now(UTC)
assert card.is_stale is False
```
