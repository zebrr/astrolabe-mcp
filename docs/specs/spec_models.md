# spec_models — Data Models

Status: READY

## Overview

Pydantic models defining all data contracts for astrolabe-mcp: configuration, document index, and tool responses.

## Models

### AppConfig

Application configuration loaded from `config.json`.

```python
class AppConfig(BaseModel):
    projects: dict[str, Path]          # name → absolute path (shared projects)
    index_dir: Path                    # directory for shared index files (relative to config dir)
    storage: Literal["json", "sqlite"] = "json"  # storage backend
    index_extensions: list[str]        # e.g. [".md", ".yaml"]
    ignore_dirs: list[str]             # directory names to skip
    ignore_files: list[str]            # glob patterns for files to skip
    max_file_size_kb: int              # max file size for full read (without section/range)
    default_list_limit: int = 50       # default limit for list_docs pagination
    default_search_limit: int = 20     # default max_results for search_docs

    # Private index (optional)
    private_projects: dict[str, Path] = {}    # name → absolute path (private projects)
    private_index_dir: Path | None = None     # directory for private index files
```

- `projects`: keys are project IDs used in doc_id, values are absolute paths (shared, cloud-synced)
- `private_projects`: same format, but stored in local-only private index
- Non-existent project paths are kept in config but skipped at scan time (not at load time)
- `index_dir`: resolved relative to config file directory. Server places `.doc-index.json` or `.doc-index.db` inside.
- `private_index_dir`: resolved relative to config file directory. Same file naming as `index_dir`. `None` if no private projects.
- `storage`: `"json"` (default) uses `.doc-index.json`, `"sqlite"` uses `.doc-index.db`. Applies to both shared and private storages.

Validations:
- If `private_projects` is non-empty and `private_index_dir` is `None` → `ValueError`
- If keys of `projects` and `private_projects` overlap → `ValueError`

Computed properties:
- `all_projects: dict[str, Path]` — `{**projects, **private_projects}`. Used everywhere the server needs the full project set.
- `is_private(project_id: str) -> bool` — `project_id in private_projects`. Used to route saves to the correct storage.

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
    date: str | None = None                   # YYYY-MM-DD, semantic document date
    enriched_at: datetime | None = None
    enriched_content_hash: str | None = None  # content_hash snapshot at enrichment time

    # Divergence tracking (null until a duplicate group splits)
    diverged_from: list[str] | None = None    # former siblings (doc_ids) whose hash no longer matches
```

Date semantics:
- `date` is a **semantic content date** (when the event happened, period ended, document was issued) — distinct from `modified` (file mtime) and `enriched_at` (enrichment time).
- Format is strictly `YYYY-MM-DD`. Partial dates (YYYY-MM, YYYY) are not accepted — skill leaves the field empty instead.
- For documents covering a range (statements, reports), the **end date** is stored.
- Optional: enrichment proceeds without `date` if the document has no identifiable date.
- Format validation lives at the write layers (`update_index_tool`, `routes_api.card_save`) — the model accepts any string. The model layer doesn't re-validate to keep SQLite roundtrips trivial.
- Shared `DATE_RE` (re.Pattern) is exported from `models.py` so MCP tool layer and Web UI reuse one regex.
- Clear semantics: `update_card` / `update_index_tool` / Web form accept the empty string `""` as the explicit clear sentinel for `date` (sets it back to `None`). `None` means "don't touch". Valid `YYYY-MM-DD` sets the value.

Computed properties:
- `doc_id: str` — `"{project}::{rel_path}"`
- `is_stale: bool` — `enriched_content_hash is not None and content_hash != enriched_content_hash` (file content changed since enrichment)
- `is_empty: bool` — `enriched_at is None`

Divergence semantics:
- `diverged_from` is an independent axis from `is_stale`. A card can be both stale and diverged, or either alone.
- Flag is carried ONLY by the card whose `content_hash` changed since the previous reindex (the "child" of the edit). Unchanged former siblings stay clean.
- Value semantics: list of `doc_id` strings that were in the card's duplicate group before the hash change and are not currently in its group.
- `None` (or empty list, never stored) means "no known divergence".
- Cleared by `reindex()` when the card's hash reconverges with at least one listed sibling, or explicitly by the `accept_divergence` MCP tool.

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
    stale_count: int = 0
    empty_count: int = 0
    desync_count: int = 0          # files missing on disk (runtime check)
    diverged_count: int = 0        # cards with non-empty diverged_from
    dated_count: int = 0           # cards with non-null date
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
    desync_documents: int = 0      # files missing on disk (project in config)
    diverged_documents: int = 0    # cards with non-empty diverged_from
    dated_documents: int = 0       # cards with non-null date
    embeddings_enabled: bool = False
    embedded_chunks: int = 0
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
    project="my-project",
    filename="README.md",
    rel_path="README.md",
    size=1200,
    modified=datetime(2026, 3, 6),
    content_hash="abc123",
)
assert card.doc_id == "my-project::README.md"
assert card.is_empty is True

# Enrich
card.type = "project_doc"
card.summary = "Main project readme"
card.enriched_at = datetime.now(UTC)
assert card.is_stale is False
```
