# spec_index — Index Core

Status: READY

## Overview

Core module: filesystem scanning, index building/loading/saving, content hashing, stale detection, enrichment updates, and reindexing. Uses `filelock` for concurrent access to `.doc-index.json`.

Note: `load_index()` and `save_index()` are used by `JsonStorage` (storage_json.py). The server does not call them directly — it uses the `StorageBackend` protocol via `storage.py`.

## Public API

### `scan_project(project_id: str, project_path: Path, config: AppConfig) -> list[DocCard]`

Discover files in a project directory and create DocCard entries for all matching files.

**File discovery** (two-tier):
1. **Git-aware** (primary): uses `git ls-files --cached --others --exclude-standard` — returns tracked files + untracked non-ignored files. Gitignored files are automatically excluded.
2. **Fallback** (`rglob`): if project is not a git repo or git is not installed, falls back to `project_path.rglob("*")`.

**Filtering** (applied uniformly to both sources):
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

### `reindex(config: AppConfig, existing: IndexData | None = None, *, mode: Literal["update", "clean", "rebuild"] = "update") -> tuple[IndexData, ReindexStats]`

Rescan filesystem and merge with existing index.

- New files: added with empty enrichment
- Changed files (content_hash mismatch): file metadata updated, card marked stale (enrichment preserved)
- Unchanged files: kept as-is
- **Pass-through**: cards from projects NOT in `config.projects` are preserved as-is (not removed)
- **Desync**: cards from projects in config where file is missing on disk are preserved as desync (not removed)

**Modes** (escalating):

| mode | Missing files (desync) | Enrichment | Move detection | Divergence detection |
|------|----------------------|------------|----------------|----------------------|
| `update` | preserved | preserved | yes | yes |
| `clean` | removed | preserved | skipped | skipped |
| `rebuild` | removed | reset | skipped | skipped (flags cleared with enrichment) |

Pass-through cards are always preserved regardless of mode.
- Returns updated IndexData + stats

### `update_card(index: IndexData, doc_id: str, *, type: str | None = None, summary: str | None = None, keywords: list[str] | None = None, headings: list[str] | None = None) -> DocCard`

Update enrichment fields on a card. Only updates fields that are explicitly passed (not None).

- Sets `enriched_at` to current UTC time
- Sets `enriched_content_hash` to current `content_hash` (snapshot at enrichment time)
- Raises `KeyError` if doc_id not in index
- Returns the updated card

### `build_hash_map(documents: dict[str, DocCard]) -> dict[str, list[str]]`

Build reverse index: `content_hash → [doc_ids]` for duplicate detection.

- Returns only hashes that appear more than once (duplicates)
- Used by server tools (search_docs, list_docs, get_card) for on-the-fly dedup
- O(n) scan over all documents, no persistent storage

### `ReindexStats` (dataclass)

```python
@dataclass
class ReindexStats:
    scanned: int
    new: int
    removed: int
    stale: int
    unchanged: int
    passthrough: int    # cards from projects not in config, preserved as-is
    desync: int         # cards where file is missing on disk (project in config)
    auto_transferred: list[tuple[str, str]]  # (old_doc_id, new_doc_id) — auto-transferred moves
    ambiguous_moves: list[dict]              # {hash, desync_ids, new_ids} — need manual resolution
    new_divergences: list[dict]              # {doc_id, diverged_from} — first-time splits in this run
```

### Move detection

After merge, reindex detects file moves/renames by matching `content_hash` between enriched desync cards (file missing) and new empty cards (file appeared).

**Algorithm:**
1. Group enriched desync cards by `content_hash` → `desync_by_hash`
2. Group new empty cards (from fresh scan only) by `content_hash` → `new_by_hash`
3. For each matching hash:
   - **1 desync : 1 new** → auto-transfer enrichment (type, summary, keywords, headings, enriched_at) from old to new card, remove old card from index, record in `auto_transferred`
   - **Any other ratio** → record in `ambiguous_moves` for manual resolution via `update_index_tool()`
   - **No match** → cards are independent, no action

Only enriched desync cards are candidates — unenriched cards have nothing to transfer. Only runs in `mode="update"` (skipped in `clean` and `rebuild`).

### Divergence detection

After move detection, reindex detects cards that have left or re-joined their duplicate groups since the previous run. Only runs in `mode="update"` (skipped in `clean`; in `rebuild` all flags are reset along with enrichment).

**Inputs:**
- `old_hash_map` = `build_hash_map(existing.documents)` — duplicate groups before the merge
- `new_hash_map` = `build_hash_map(new_documents)` — duplicate groups after the merge

**Per-card logic** (for every card in `new_documents`):

1. `previous_flag` = the card's prior `diverged_from` value (empty list if never flagged or brand-new).
2. `old_content_hash` = the card's hash before this reindex (from `existing.documents[doc_id]`), or `None` for brand-new cards.
3. `old_siblings` = other `doc_id`s that shared `old_content_hash` in the old index (empty if not in a group or brand-new).
4. `current_copies` = other `doc_id`s sharing the card's current `content_hash` in `new_documents`.
5. `fresh_drift` = `old_siblings − current_copies` (siblings who didn't follow into the new group). Only meaningful when the hash changed; otherwise `old_siblings == current_copies ∪ nothing`, producing an empty set.
6. `merged = (previous_flag ∪ fresh_drift) ∩ new_documents.keys() − current_copies` — union existing drift with any fresh drift, drop entries that no longer exist in the index, drop entries that have re-joined the current group.
7. Set `card.diverged_from = merged if merged else None`.
8. If `merged` is non-empty AND `previous_flag` was empty → record in `stats.new_divergences` (first-time split in this run).

**Invariants:**
- Only cards whose hash changed (or were already flagged) can have a non-empty `diverged_from`; unchanged cards with unchanged siblings stay clean.
- When all original siblings edit in lockstep (group moves together), `fresh_drift` is empty → no flag set.
- Partial reconvergence (some listed siblings re-match the current hash) narrows the list; full reconvergence clears it.
- `accept_divergence` explicitly sets `diverged_from = None` without touching `content_hash` or enrichment — complementary to automatic clearing.

## Internal Functions

### `_compute_hash(file_path: Path) -> str`

MD5 hex digest of file contents via `Path.read_bytes()`. Normalizes line endings (`\r\n` → `\n`) before hashing to ensure cross-platform consistency.

### `_matches_ignore_files(filename: str, patterns: list[str]) -> bool`

Check if filename matches any glob pattern from ignore_files.

### `_list_files_git(project_path: Path) -> list[Path] | None`

List files via `git ls-files --cached --others --exclude-standard`.

- Returns list of absolute Paths on success
- Returns `None` if not a git repo (non-zero returncode) or git not installed (`FileNotFoundError`)
- Returns empty list for valid git repo with no files
- Uses `encoding="utf-8"` explicitly (git outputs UTF-8; Windows default cp1252 breaks on non-ASCII paths)
- Timeout: 30 seconds
- Logs at INFO level when falling back to rglob

### `_list_files_rglob(project_path: Path) -> list[Path]`

List files via `project_path.rglob("*")`. Filters to `is_file()` and not `is_symlink()`.

Fallback for non-git directories.

## Dependencies

- `astrolabe.models` (AppConfig, DocCard, IndexData)
- `filelock`
- `subprocess`, `hashlib`, `json`, `logging`, `datetime`, `pathlib`, `fnmatch`, `tempfile` (stdlib)

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
