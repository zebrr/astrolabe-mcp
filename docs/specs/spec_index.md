# spec_index — Index Core

Status: READY

## Overview

Core module: filesystem scanning, index building/loading/saving, content hashing, stale detection, enrichment updates, and reindexing. Uses `filelock` for concurrent access to `.doc-index.json`.

## Public API

### `scan_project(project_id: str, project_path: Path, config: AppConfig) -> list[DocCard]`

Walk a project directory and create DocCard entries for all matching files.

- Skips directories whose name is in `config.ignore_dirs`
- Skips files matching any `config.ignore_files` glob pattern
- Only includes files with extensions in `config.index_extensions`
- Does not follow symlinks
- Computes MD5 content_hash for each file
- `rel_path` stored as POSIX string (forward slashes)
- Returns list of DocCards (no enrichment fields set)

### `load_index(index_path: Path) -> IndexData | None`

Load existing index from disk.

- Returns `None` if file does not exist
- Uses `filelock` during read
- On JSON decode error or validation error: backs up corrupt file as `.bak`, returns `None`

### `save_index(index: IndexData, index_path: Path) -> None`

Save index to disk atomically.

- Uses `filelock` during write
- `json.dumps(ensure_ascii=False, indent=2)`
- Writes to temp file first, then renames (atomic on POSIX)

### `build_index(config: AppConfig) -> IndexData`

Full index build from scratch. Scans all projects, creates IndexData.

- Skips non-existent project paths with a warning (via `logging`)
- Sets `indexed_at` to current UTC time

### `reindex(config: AppConfig, existing: IndexData | None = None) -> tuple[IndexData, ReindexStats]`

Rescan filesystem and merge with existing index.

- New files: added with empty enrichment
- Removed files: deleted from index
- Changed files (content_hash mismatch): file metadata updated, card marked stale (enrichment preserved)
- Unchanged files: kept as-is
- Returns updated IndexData + stats

### `update_card(index: IndexData, doc_id: str, *, type: str | None = None, summary: str | None = None, keywords: list[str] | None = None, headings: list[str] | None = None) -> DocCard`

Update enrichment fields on a card. Only updates fields that are explicitly passed (not None).

- Sets `enriched_at` to current UTC time
- Raises `KeyError` if doc_id not in index
- Returns the updated card

### `ReindexStats` (dataclass)

```python
@dataclass
class ReindexStats:
    scanned: int
    new: int
    removed: int
    stale: int
    unchanged: int
```

## Internal Functions

### `_compute_hash(file_path: Path) -> str`

MD5 hex digest of file contents via `Path.read_bytes()`.

### `_matches_ignore_files(filename: str, patterns: list[str]) -> bool`

Check if filename matches any glob pattern from ignore_files.

## Dependencies

- `astrolabe.models` (AppConfig, DocCard, IndexData)
- `filelock`
- `hashlib`, `json`, `logging`, `datetime`, `pathlib`, `fnmatch`, `tempfile` (stdlib)

## Data Flow

```
build_index:  config → scan_project(per project) → IndexData → save_index
reindex:      config + existing IndexData → scan → merge → IndexData + stats → save_index
update_card:  IndexData + doc_id + fields → mutated DocCard
```

## Error Handling

- Non-existent project path: `logging.warning()`, skip
- Corrupt index file: backup as `.bak`, return None from load_index
- File read error during scan: `logging.warning()`, skip file
- doc_id not found in update_card: `KeyError`
