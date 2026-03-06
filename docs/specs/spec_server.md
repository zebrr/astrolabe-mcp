# spec_server — MCP Server

Status: READY

## Overview

MCP server exposing 7 tools over stdio transport. Wraps core modules (index, reader, search, config). Auto-reindexes on startup.

## Startup Sequence

1. Resolve config path from `ASTROLABE_CONFIG` env var (default: `config.json` in server's directory)
2. `load_config(config_path)`
3. `load_doc_types(config_path.parent / "doc_types.yaml")`
4. `load_index(config.index_path)` → if exists, `reindex(config, existing)` → `save_index()`
5. If no existing index: `build_index(config)` → `save_index()`
6. Start MCP server on stdio

## MCP Tools (7)

### `get_cosmos() -> CosmosResponse`

Entry point. Returns projects, document types, index stats.
- Builds CosmosResponse from current index + doc_types
- `document_types` from real index (only assigned types), descriptions from doc_types.yaml

### `list_docs(project?, type?, stale?) -> list[DocCard summary]`

List document cards with optional filters.
- `stale=true`: only cards where `is_stale or is_empty`
- Returns card summaries (doc_id, project, type, filename, summary, keywords, modified, enriched_at)

### `search_docs(query, project?, type?) -> list[SearchResult]`

Search by query with field weights. Delegates to `search.search()`.

### `read_doc(doc_id) -> DocCard full`

Full card metadata for a specific document. No file content.
- Raises error if doc_id not found

### `get_doc(doc_id, section?, range?) -> file content`

Read file content. Delegates to `reader.read_file()`.
- Resolves absolute path from config.projects[card.project] / card.rel_path
- Returns content + metadata (total_lines, returned_lines, section, truncated)
- Raises error if doc_id not found or file missing

### `update_index(doc_id, type?, summary?, keywords?, headings?) -> update confirmation`

Agent enriches a card. Delegates to `index.update_card()`, then `save_index()`.
- Returns updated fields list + enriched_at timestamp

### `reindex(project?) -> ReindexStats`

Rescan filesystem. If project given, only rescan that project (rebuild full index but filter scan).
- Delegates to `index.reindex()`, then `save_index()`

## Error Handling

All tools return structured JSON. Errors include:
- `error`: error message
- `hint`: actionable suggestion (e.g. "run reindex()" if file missing)

## Dependencies

- `mcp` SDK
- `astrolabe.config`, `astrolabe.index`, `astrolabe.reader`, `astrolabe.search`, `astrolabe.models`
- `os`, `pathlib`, `logging` (stdlib)
