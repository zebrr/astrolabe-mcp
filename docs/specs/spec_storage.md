# spec_storage — Storage Abstraction

Status: READY

## Overview

Pluggable storage layer for the document index. Abstracts away the persistence mechanism behind a `StorageBackend` Protocol, allowing the server to work with JSON files (current behavior) or SQLite databases (new) without changing tool logic.

The server continues to hold `IndexData` in memory for reads. The storage backend handles persistence — full index save/load and single-card writes. SQLite optimizes the write path: single INSERT OR REPLACE instead of full-file rewrite.

## StorageBackend Protocol

```python
from typing import Protocol, runtime_checkable
from datetime import datetime
from pathlib import Path

from astrolabe.models import DocCard, IndexData


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for index storage backends."""

    def load(self) -> IndexData | None:
        """Load entire index from storage.

        Returns None if storage does not exist or is corrupt.
        Corrupt storage should be backed up before returning None.
        """
        ...

    def save(self, index: IndexData) -> None:
        """Save entire index (full overwrite).

        Used after build_index() and reindex() — bulk operations
        where the full index has changed.
        """
        ...

    def save_card(self, card: DocCard, indexed_at: datetime) -> None:
        """Persist a single card (upsert).

        Used after update_card() — enrichment of individual cards.
        For JsonStorage: rewrites entire file (same as current behavior).
        For SqliteStorage: single INSERT OR REPLACE (the key optimization).

        Args:
            card: The card to persist.
            indexed_at: Current index timestamp (for meta table in SQLite).
        """
        ...

    def exists(self) -> bool:
        """Check if storage file/database exists on disk."""
        ...

    @property
    def path(self) -> Path:
        """Path to the storage file (.json or .db)."""
        ...
```

## Factory Functions

### `create_storage_at(index_dir, storage_type) -> StorageBackend`

Core factory. Creates a storage backend for a given directory. Creates `index_dir` if it does not exist (`mkdir -p`).

```python
def create_storage_at(index_dir: Path, storage_type: str) -> StorageBackend:
    """Create storage backend for a specific directory.

    Args:
        index_dir: Directory for index files.
        storage_type: "json" or "sqlite".

    Returns:
        JsonStorage or SqliteStorage instance.

    Migration:
        If storage_type is "sqlite" and the .db file does not exist
        but the .json file does, auto-migrates JSON -> SQLite.
    """
```

Used directly by the server to create both shared and private storages.

### `create_storage(config) -> StorageBackend`

Convenience wrapper for backward compatibility.

```python
def create_storage(config: AppConfig) -> StorageBackend:
    """Create shared storage backend based on config.

    Delegates to create_storage_at(config.index_dir, config.storage).
    """
```

### Path resolution

- `index_dir` is a directory. Factory constructs filenames:
  - `storage_type == "json"`: `index_dir / ".doc-index.json"`
  - `storage_type == "sqlite"`: `index_dir / ".doc-index.db"`

### Migration logic (in `create_storage_at`)

When `storage_type == "sqlite"`:
1. `json_path = index_dir / ".doc-index.json"`, `db_path = index_dir / ".doc-index.db"`
2. If `db_path` does not exist but `json_path` does:
   - Load JSON index via `load_index(json_path)`
   - Create SqliteStorage at `db_path`
   - Call `storage.save(json_index)` to bulk-insert all cards
   - Log: "Migrated N cards from JSON to SQLite"
3. If both exist: use SQLite (authoritative after migration)
4. If neither exists: return empty SqliteStorage (will be populated by build_index)
5. JSON file is NOT deleted (backup, can switch back)

## JsonStorage

Wraps existing `load_index()` and `save_index()` from `index.py`.

```python
class JsonStorage:
    """JSON file storage backend.

    Delegates to load_index/save_index in index.py.
    Same behavior as pre-abstraction code.
    """

    def __init__(self, index_path: Path) -> None: ...

    def load(self) -> IndexData | None: ...
        # Delegates to index.load_index(self._path)

    def save(self, index: IndexData) -> None: ...
        # Delegates to index.save_index(index, self._path)

    def save_card(self, card: DocCard, indexed_at: datetime) -> None: ...
        # Load full index, update card in documents dict,
        # save full index. Same write amplification as before.

    def exists(self) -> bool: ...
        # self._path.exists()

    @property
    def path(self) -> Path: ...
        # self._path
```

### save_card implementation detail

JsonStorage.save_card must handle the case where the index file doesn't exist yet (e.g. during initial enrichment before first save). It loads the current index, updates the card, sets indexed_at, and saves:

```python
def save_card(self, card: DocCard, indexed_at: datetime) -> None:
    index = load_index(self._path)
    if index is None:
        index = IndexData(indexed_at=indexed_at, documents={})
    index.documents[card.doc_id] = card
    index.indexed_at = indexed_at
    save_index(index, self._path)
```

## SqliteStorage

SQLite-based storage using stdlib `sqlite3`. No external dependencies.

```python
class SqliteStorage:
    """SQLite storage backend.

    Uses journal_mode=DELETE for cloud drive compatibility.
    Stores headings and keywords as JSON-encoded strings.
    """

    def __init__(self, db_path: Path) -> None: ...
        # Opens/creates DB, sets journal_mode=DELETE,
        # creates tables if not exist

    def load(self) -> IndexData | None: ...
        # Read all rows from documents table,
        # read meta table for version + indexed_at,
        # return IndexData

    def save(self, index: IndexData) -> None: ...
        # BEGIN TRANSACTION
        # DELETE FROM documents
        # DELETE FROM meta
        # INSERT all cards + meta
        # COMMIT

    def save_card(self, card: DocCard, indexed_at: datetime) -> None: ...
        # INSERT OR REPLACE INTO documents VALUES (...)
        # UPDATE meta SET value=indexed_at WHERE key='indexed_at'

    def exists(self) -> bool: ...
        # self._path.exists()

    @property
    def path(self) -> Path: ...
        # self._path
```

### Schema

```sql
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id                TEXT PRIMARY KEY,
    project               TEXT NOT NULL,
    filename              TEXT NOT NULL,
    rel_path              TEXT NOT NULL,
    size                  INTEGER NOT NULL,
    modified              TEXT NOT NULL,
    content_hash          TEXT NOT NULL,
    type                  TEXT,
    headings              TEXT,
    summary               TEXT,
    keywords              TEXT,
    enriched_at           TEXT,
    enriched_content_hash TEXT,
    diverged_from         TEXT   -- JSON array of doc_ids, NULL when no divergence
);

CREATE INDEX IF NOT EXISTS idx_project ON documents(project);
CREATE INDEX IF NOT EXISTS idx_type ON documents(type);
```

### Data conversion

- **Timestamps**: ISO 8601 strings (`datetime.isoformat()` / `datetime.fromisoformat()`)
- **headings, keywords, diverged_from**: `json.dumps(list)` / `json.loads(str)`, NULL if None or empty
- **size**: INTEGER (native SQLite)
- **All other fields**: TEXT

### Migration pattern

New columns are added on open via `ALTER TABLE ... ADD COLUMN` wrapped in `contextlib.suppress(sqlite3.OperationalError)`. The suppress catches the "duplicate column" error raised when the column already exists, so old and new databases both work. Example:

```python
with contextlib.suppress(sqlite3.OperationalError):
    self._conn.execute("ALTER TABLE documents ADD COLUMN diverged_from TEXT")
```

Used historically for `enriched_content_hash` and now for `diverged_from`. Pre-existing databases without the column load with `diverged_from = None` (no divergence flag).

### Connection management

- Single `sqlite3.Connection` created in `__init__`, kept for the lifetime of the storage object
- `journal_mode=DELETE` set via PRAGMA on connection
- No connection pooling needed (single server process)
- Connection closed in `__del__` or via explicit `close()` method

### Concurrency

- `journal_mode=DELETE` handles file-level locking
- No filelock needed (SQLite handles its own locking)
- Safe for single-writer scenarios (MCP server is single-process)
- Cloud drive: single .db file, no -wal/-shm auxiliary files

## Module Layout

```
src/astrolabe/
├── storage.py          # StorageBackend Protocol + create_storage() factory
├── storage_json.py     # JsonStorage class
├── storage_sqlite.py   # SqliteStorage class
├── index.py            # Unchanged — load_index/save_index used by JsonStorage
└── server.py           # Refactored — uses StorageBackend instead of direct calls
```

## Dependencies

- `sqlite3` (stdlib) — used by SqliteStorage
- `json` (stdlib) — used for headings/keywords serialization
- `filelock` — still used by JsonStorage (via index.py)
- No new external dependencies

## Error Handling

- Corrupt SQLite DB: log warning, return None from load()
- Missing meta table: treat as non-existent DB, return None from load()
- Migration failure: transaction rollback, log error, raise exception (don't silently continue with empty index)
- File permission errors: propagate as-is (same as current JSON behavior)
