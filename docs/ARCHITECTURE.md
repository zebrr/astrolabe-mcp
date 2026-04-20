# Architecture — astrolabe-mcp

## Overview

Python MCP server that creates a knowledge layer across multiple projects. Dumb server (file walking, index, serving) + smart agent (classification, descriptions via `update_index`).

Requirements: `docs/CONCEPT.md`

## Project Structure

```
astrolabe-mcp/
├── CLAUDE.md               # agent mechanics
├── README.md               # user-facing docs
├── pyproject.toml           # dependencies and tool config
├── .gitignore
├── runtime/                 # server runtime (not committed except examples)
│   ├── config.example.json  # config template
│   ├── doc_types.example.yaml # doc type template
│   ├── config.json          # actual config (gitignored)
│   ├── doc_types.yaml       # actual doc types (gitignored)
│   └── .doc-index.json      # generated index (gitignored)
├── docs/
│   ├── CONCEPT.md           # requirements (read-only)
│   ├── ARCHITECTURE.md      # this file
│   ├── PLAN.md              # current milestone
│   ├── PROGRESS.md          # progress log
│   ├── specs/               # module specifications
│   ├── skills_drafts/       # draft skills (before moving to .claude/skills/)
│   └── archive/             # archived plans/progress
├── src/astrolabe/
│   ├── models.py            # Pydantic data models
│   ├── config.py            # config loading
│   ├── index.py             # FS scanning, index, stale detection
│   ├── reader.py            # file reading, section extraction
│   ├── search.py            # text search + hybrid stem/embedding search
│   ├── chunker.py           # file content chunking for embeddings
│   ├── embeddings.py        # EmbeddingBackend Protocol + factory
│   ├── embeddings_chroma.py # ChromaDB implementation (optional)
│   ├── storage.py           # StorageBackend Protocol + factory
│   ├── storage_json.py      # JSON file storage backend
│   ├── storage_sqlite.py    # SQLite storage backend
│   ├── server.py            # MCP transport: tools → core
│   └── web/                 # Web UI transport (optional)
│       ├── __init__.py
│       ├── __main__.py      # python -m astrolabe.web
│       ├── app.py           # FastAPI factory, lifespan
│       ├── state.py         # AppState: config, index, storage
│       ├── routes_pages.py  # HTML page routes
│       ├── routes_api.py    # HTMX API routes
│       ├── templates/       # Jinja2 templates
│       └── static/          # Pico CSS, HTMX, custom CSS
└── tests/                   # pytest, tmp_path fixtures
```

## Modules

| Module | Status | Spec | Purpose |
|--------|--------|------|---------|
| models.py | done | spec_models.md | Data contracts: AppConfig (shared+private projects), DocCard, IndexData, SearchResult, CosmosResponse |
| config.py | done | spec_config.md | Load config.json + doc_types.yaml, resolve private_index_dir |
| index.py | done | spec_index.md | Core: git-aware scan, build/load/save index, hash, stale detection |
| reader.py | done | spec_reader.md | Read files: full, by section heading, by line range |
| search.py | done | spec_search.md | Bilingual stem matching (EN+RU) + hybrid stem/embedding search |
| chunker.py | done | spec_chunker.md | File content chunking for embedding (paragraph-aware) |
| embeddings.py | done | spec_embeddings.md | EmbeddingBackend Protocol + factory + availability check |
| embeddings_chroma.py | done | spec_embeddings.md | ChromaDB implementation (optional, lazy init) |
| storage.py | done | spec_storage.md | StorageBackend Protocol + create_storage() factory |
| storage_json.py | done | spec_storage.md | JSON file backend (wraps index.py load/save) |
| storage_sqlite.py | done | spec_storage.md | SQLite backend (single-row upserts, cloud-safe) |
| server.py | done | spec_server.md | 10 MCP tools wrapping core functions via StorageBackend |
| web/ | done | spec_web.md | Local web UI: FastAPI + Jinja2 + HTMX. Card editing, search, doc reader |

## Dependencies

```
models.py ← config.py ← index.py ← storage_json.py ← storage.py ← server.py
models.py ← reader.py ←──────────────────────────────────────────────┘
models.py ← search.py ←──────────────────────────────────────────────┘
chunker.py ← embeddings.py ← embeddings_chroma.py ←──────────────────┘
models.py ← storage_sqlite.py ← storage.py
                                                                      ← web/state.py ← web/app.py
```

## MCP Tools (10)

`get_doc_types`, `get_cosmos`, `list_docs`, `search_docs`, `deep_search`, `get_card`, `read_doc`, `update_index`, `reindex`, `accept_divergence`

See `docs/CONCEPT.md` for full tool specifications.

## Key Technical Decisions

- Pluggable storage: JSON (`.doc-index.json`, filelock) or SQLite (`.doc-index.db`, journal_mode=DELETE)
- Config switch: `"storage": "json"` (default) or `"storage": "sqlite"`
- Auto-migration: switching config to sqlite auto-converts existing JSON index
- SQLite: single-row upserts for enrichment (vs full-file rewrite in JSON)
- Git-aware scanning: `scan_project()` uses `git ls-files` as primary source, falls back to `rglob("*")` for non-git directories. Gitignored files excluded automatically; `ignore_dirs`/`ignore_files` only needed for domain-specific exclusions (e.g. `src/` tracked by git but not wanted in index)
- Content hash: MD5 with CRLF→LF normalization for cross-platform consistency
- Search: bilingual stem matching (EN+RU via snowballstemmer) with field weights (keywords 3.0, headings 2.0, summary 1.5, filename 0.8)
- Cross-platform: pathlib everywhere, rel_path as POSIX strings
- Shared index: pass-through for foreign project cards, desync detection for missing files
- Private index: separate storage for private projects, merged transparently in memory, save routing by project
- Stale detection: hash-based (`enriched_content_hash` vs `content_hash`), not timestamp-based
- Reindex modes: `update` (preserve all) → `clean` (remove desync) → `rebuild` (reset enrichment)
- doc_types.yaml: single shared vocabulary. `get_doc_types()` tool returns full structure. Type validation in `update_index`.
- doc_types.yaml lookup: `index_dir` first, fallback to `config_path.parent` (shared vocabulary in cloud sync)
- Output optimization (v0.7.0): `list_docs`/`search_docs` return envelope `{total, limit/max_results, result, hint?}` with pagination and adaptive agent hints. Timestamps stripped from list/search output (kept in `get_card`). Defaults in AppConfig (`default_list_limit=50`, `default_search_limit=20`)
- Content deduplication (v0.7.2): documents with identical `content_hash` across projects are detected on-the-fly via `build_hash_map()`. `search_docs` collapses duplicates (first by relevance wins). `list_docs` marks copies with `has_copies: true`. `get_card` lists all copies in `copies: [doc_id, ...]`. No storage changes — computed at query time.
- Web UI (v0.8.0): Local browser interface via FastAPI + Jinja2 + HTMX. Separate process from MCP server, shared storage. Optional `[web]` dependencies. Launch: `.venv/bin/python -m astrolabe.web`. AppState class extracts server.py's global state pattern into a proper class. Card inline editing, markdown doc reader, live search, reindex actions.
- Semantic search (v0.9.0): Optional ChromaDB-based `deep_search` tool for semantic search over file content. Enabled with `"embeddings": true` in config, requires `pip install astrolabe-mcp[embeddings]`. Files chunked and embedded at reindex time — works even without enrichment. Separate from `search_docs` (fast stem matching) — `deep_search` is on-demand for when keyword search finds too few results. Cross-hints between tools guide the agent. Lazy init — model loaded on first deep_search call.
- Embeddings local storage (v0.9.2): ChromaDB data stored locally (`runtime/.chromadb/`, configurable via `embeddings_dir`), not on cloud drives — HNSW files are too large for reliable cloud sync. Single backend for all projects (no shared/private split). Manifest-based sync (`manifest.json`) tracks embedded doc_ids + content_hashes — handles first launch, partial embeddings, incremental updates without unnecessary rebuilds. Web UI has no embedding code — only MCP server uses embeddings.
- Divergence detection (v0.9.3): when a card whose hash previously matched siblings (duplicate group) gets edited, the edited card's `diverged_from` is set to the list of former siblings who no longer share the hash. Detection runs at reindex (update mode), ortogonal to `is_stale`. Only the card whose hash actually changed carries the flag; unchanged siblings stay clean. On subsequent reindex, list narrows when any listed sibling reconverges; full reconvergence clears the flag. Manual resolution via new `accept_divergence(doc_id)` tool for the "intentional fork" case, or natural reconvergence by editing remaining siblings to match.
- Semantic date field (v0.10.0): optional `DocCard.date` (strict `YYYY-MM-DD`, empty when absent) carries the document's content date — statement period end, receipt date, report date — distinct from `modified` (mtime) and `enriched_at`. Extracted by the `enrich-index` skill only when a full day is present; date ranges in a document resolve to the end date. Filtering: `list_docs` / `search_docs` accept `date_from` / `date_to` (inclusive); cards without date are excluded when any bound is set. Sorting: `sort="date_desc"|"date_asc"` in `list_docs`; `search_docs` adds the same plus the default `"relevance"`. Undated cards always sort to the end. `get_cosmos` exposes `dated_documents` (global) and `dated_count` (per project). SQLite gets a new `date` column auto-migrated via ALTER TABLE. Format validation lives at the tool layer (regex), returning an error dict on mismatch.
