# spec_server — MCP Server

Status: READY

## Overview

MCP server exposing 7 tools over stdio transport. Wraps core modules (index, reader, search, config). Auto-reindexes on startup.

## Startup Sequence

1. Resolve config path from `ASTROLABE_CONFIG` env var (default: `runtime/config.json`)
2. `load_config(config_path)`
3. Load `doc_types.yaml`: look in `config.index_dir` first, fallback to `config_path.parent`
4. `_storage = create_storage(config)` (auto-migrates JSON→SQLite if needed)
5. `_storage.load()` → if exists, `reindex(config, existing)` → `_storage.save()`
6. If no existing index: `build_index(config)` → `_storage.save()`
7. Start MCP server on stdio

## MCP Tools (7)

### `get_cosmos() -> CosmosResponse`

Entry point. Returns projects, document types, index stats.
- Builds CosmosResponse from current index + doc_types
- `document_types` from real index (only assigned types), descriptions from doc_types.yaml
- `desync_documents`: count of cards where file missing on disk (project in config) or `enriched_at > modified`

### `list_docs(project?, type?, stale?) -> list[DocCard summary]`

List document cards with optional filters.
- `stale=true`: only cards where `is_stale or is_empty`
- Returns card summaries (doc_id, project, type, filename, summary, keywords, modified, enriched_at)

### `search_docs(query, project?, type?) -> list[SearchResult]`

Search by query with field weights. Delegates to `search.search()`.

### `get_card(doc_id) -> DocCard full`

Index card metadata for a specific document. No file content.
- Raises error if doc_id not found

### `read_doc(doc_id, section?, range?) -> file content`

Read document content from disk. Delegates to `reader.read_file()`.
- Resolves absolute path from config.projects[card.project] / card.rel_path
- Returns content + metadata (total_lines, returned_lines, section, truncated)
- Raises error if doc_id not found or file missing

### `update_index(doc_id, type?, summary?, keywords?, headings?) -> update confirmation`

Agent enriches a card. Delegates to `index.update_card()`, then `_storage.save_card()`.
- Returns updated fields list + enriched_at timestamp
- SQLite: single INSERT OR REPLACE (~1KB). JSON: full file rewrite.

### `reindex(project?, mode?) -> ReindexStats`

Rescan filesystem. If project given, only rescan that project (rebuild full index but filter scan).
- Reloads config from disk to pick up changes (projects, storage, extensions)
- Recreates `_storage` via `create_storage()` in case `config.storage` changed
- `mode`: `"update"` (default) | `"clean"` (remove desync, keep enrichment) | `"rebuild"` (remove desync, reset enrichment)
- Pass-through cards always preserved regardless of mode
- Delegates to `index.reindex()`, then `_storage.save()`
- Returns stats including `passthrough`, `desync`, and `potential_moves`

## Error Handling

All tools return structured JSON. Errors include:
- `error`: error message
- `hint`: actionable suggestion (e.g. "run reindex()" if file missing)

## Global State

- `_config: AppConfig | None` — loaded config
- `_index: IndexData | None` — in-memory index (all reads go here)
- `_storage: StorageBackend | None` — persistence backend (writes go here)
- `_doc_types: dict[str, str]` — document type descriptions from doc_types.yaml

## Dependencies

- `mcp` SDK
- `astrolabe.__version__`, `astrolabe.config`, `astrolabe.index`, `astrolabe.reader`, `astrolabe.search`, `astrolabe.models`
- `astrolabe.storage` (StorageBackend, create_storage)
- `os`, `pathlib`, `logging` (stdlib)
