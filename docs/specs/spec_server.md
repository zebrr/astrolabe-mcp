# spec_server — MCP Server

Status: READY

## Overview

MCP server exposing 8 tools over stdio transport. Wraps core modules (index, reader, search, config). Auto-reindexes on startup.

## Startup Sequence

1. Resolve config path from `ASTROLABE_CONFIG` env var (default: `runtime/config.json`)
2. `load_config(config_path)`
3. Load `doc_types.yaml` via `load_doc_types_full()`: look in `config.index_dir` first, fallback to `config_path.parent`
   - Store full structure in `_doc_types_full` (for `get_doc_types()` tool)
   - Derive `_doc_types` flat mapping (for `get_cosmos()` descriptions)
4. `_storage = create_storage(config)` (shared storage, auto-migrates JSON→SQLite if needed)
5. If `config.private_index_dir` is set:
   - `_private_storage = create_storage_at(config.private_index_dir, config.storage)`
6. Load and merge indexes:
   - `shared_index = _storage.load()` (or `build_index` if not exists)
   - `private_index = _private_storage.load()` if private storage exists
   - Merge: `_index.documents = {**shared_docs, **private_docs}`
   - Reindex uses `config.all_projects` for filesystem scan
   - `_save_index()` to persist both storages
7. Start MCP server on stdio

## MCP Tools (8)

### `get_doc_types() -> dict[str, dict]`

Return the full document type vocabulary from doc_types.yaml.
- Returns `_doc_types_full` — each type has `description` (str) and `examples` (list[str], optional)
- Used by enrich-index skill for classification guidance
- Returns `{}` if doc_types.yaml is missing

### `get_cosmos() -> CosmosResponse`

Entry point. Returns projects, document types, index stats.
- Builds CosmosResponse from current index + doc_types
- Uses `config.all_projects` for project stats and desync detection
- `document_types` from real index (only assigned types), descriptions from doc_types.yaml
- `desync_documents`: count of cards where file missing on disk (project in config)

### `list_docs(project?, type?, stale?) -> list[DocCard summary]`

List document cards with optional filters.
- `stale=true`: only cards where `is_stale or is_empty`
- Returns card summaries (doc_id, project, type, filename, summary, keywords, modified, enriched_at)

### `search_docs(query, project?, type?) -> list[SearchResult]`

Search by query with field weights. Delegates to `search.search()`.

### `get_card(doc_id) -> DocCard full`

Index card metadata for a specific document. No file content.
- Includes `stale: bool` flag (true if file content changed since enrichment)
- Raises error if doc_id not found

### `read_doc(doc_id, section?, range?) -> file content`

Read document content from disk. Delegates to `reader.read_file()`.
- Resolves absolute path from `config.all_projects[card.project] / card.rel_path`
- Returns content + metadata (total_lines, returned_lines, section, truncated)
- Raises error if doc_id not found or file missing

### `update_index(doc_id, type?, summary?, keywords?, headings?) -> update confirmation`

Agent enriches a card. Delegates to `index.update_card()`, then saves to the correct storage.
- **Type validation**: if `type` is provided and `_doc_types` is non-empty, validates that `type` exists in `_doc_types` keys. Returns error: `"Unknown type '{type}'. Available types: [...]"` if not found.
- **Save routing**: determines storage by `config.is_private(card.project)` → `_private_storage.save_card()` or `_storage.save_card()`
- Returns updated fields list + enriched_at timestamp
- SQLite: single INSERT OR REPLACE (~1KB). JSON: full file rewrite.

### `reindex(project?, mode?) -> ReindexStats`

Rescan filesystem. If project given, only rescan that project (rebuild full index but filter scan).
- Reloads config from disk to pick up changes (projects, storage, extensions)
- Recreates both storages (`_storage` via `create_storage()`, `_private_storage` via `create_storage_at()` if configured)
- Uses `config.all_projects` for filesystem scan
- `mode`: `"update"` (default) | `"clean"` (remove desync, keep enrichment) | `"rebuild"` (remove desync, reset enrichment)
- Pass-through cards always preserved regardless of mode
- Delegates to `index.reindex()`, then `_save_index()` to persist with routing
- **Single project reindex**: checks `config.all_projects` (not just `config.projects`)
- Returns stats including `passthrough`, `desync`, and `potential_moves`

## Error Handling

All tools return structured JSON. Errors include:
- `error`: error message
- `hint`: actionable suggestion (e.g. "run reindex()" if file missing)

## Global State

- `_config: AppConfig | None` — loaded config
- `_index: IndexData | None` — in-memory index (all reads go here, merged from both storages)
- `_storage: StorageBackend | None` — shared persistence backend
- `_private_storage: StorageBackend | None` — private persistence backend (None if no private config)
- `_doc_types_full: dict[str, dict]` — full document type vocabulary from doc_types.yaml (description + examples)
- `_doc_types: dict[str, str]` — flat mapping type → description, derived from `_doc_types_full`

## Internal Helpers

### `_save_index()`

Splits `_index.documents` into shared and private cards based on `config.is_private(card.project)`.
- Creates two IndexData objects with split documents
- Saves shared cards to `_storage`
- Saves private cards to `_private_storage` (if exists)
- If no `_private_storage`: saves all cards to `_storage` (backward compat)

### `_get_storage_for_project(project: str) -> StorageBackend`

Returns `_private_storage` if `config.is_private(project)` and `_private_storage` exists, otherwise `_storage`.
Used by `update_index_tool()` for single-card saves.

## Dependencies

- `mcp` SDK
- `astrolabe.__version__`, `astrolabe.config`, `astrolabe.index`, `astrolabe.reader`, `astrolabe.search`, `astrolabe.models`
- `astrolabe.storage` (StorageBackend, create_storage, create_storage_at)
- `os`, `pathlib`, `logging` (stdlib)
