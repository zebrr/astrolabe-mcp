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
│   ├── search.py            # text search over enriched cards
│   ├── storage.py           # StorageBackend Protocol + factory
│   ├── storage_json.py      # JSON file storage backend
│   ├── storage_sqlite.py    # SQLite storage backend
│   └── server.py            # MCP transport: tools → core
└── tests/                   # pytest, tmp_path fixtures
```

## Modules

| Module | Status | Spec | Purpose |
|--------|--------|------|---------|
| models.py | done | spec_models.md | Data contracts: AppConfig (shared+private projects), DocCard, IndexData, SearchResult, CosmosResponse |
| config.py | done | spec_config.md | Load config.json + doc_types.yaml, resolve private_index_dir |
| index.py | done | spec_index.md | Core: scan projects, build/load/save index, hash, stale detection |
| reader.py | done | spec_reader.md | Read files: full, by section heading, by line range |
| search.py | done | spec_search.md | Token matching with field weights over enriched cards |
| storage.py | done | spec_storage.md | StorageBackend Protocol + create_storage() factory |
| storage_json.py | done | spec_storage.md | JSON file backend (wraps index.py load/save) |
| storage_sqlite.py | done | spec_storage.md | SQLite backend (single-row upserts, cloud-safe) |
| server.py | done | spec_server.md | 8 MCP tools wrapping core functions via StorageBackend |

## Dependencies

```
models.py ← config.py ← index.py ← storage_json.py ← storage.py ← server.py
models.py ← reader.py ←──────────────────────────────────────────────┘
models.py ← search.py ←──────────────────────────────────────────────┘
models.py ← storage_sqlite.py ← storage.py
```

## MCP Tools (8)

`get_doc_types`, `get_cosmos`, `list_docs`, `search_docs`, `get_card`, `read_doc`, `update_index`, `reindex`

See `docs/CONCEPT.md` for full tool specifications.

## Key Technical Decisions

- Pluggable storage: JSON (`.doc-index.json`, filelock) or SQLite (`.doc-index.db`, journal_mode=DELETE)
- Config switch: `"storage": "json"` (default) or `"storage": "sqlite"`
- Auto-migration: switching config to sqlite auto-converts existing JSON index
- SQLite: single-row upserts for enrichment (vs full-file rewrite in JSON)
- `ignore_dirs` / `ignore_files` fully configurable in config.json
- Content hash: MD5 with CRLF→LF normalization for cross-platform consistency
- Search: token-level matching with field weights (keywords 3.0, filename 2.5, headings 2.0, summary 1.0)
- Cross-platform: pathlib everywhere, rel_path as POSIX strings
- Shared index: pass-through for foreign project cards, desync detection for missing files
- Private index: separate storage for private projects, merged transparently in memory, save routing by project
- Stale detection: hash-based (`enriched_content_hash` vs `content_hash`), not timestamp-based
- Reindex modes: `update` (preserve all) → `clean` (remove desync) → `rebuild` (reset enrichment)
- doc_types.yaml: single shared vocabulary. `get_doc_types()` tool returns full structure. Type validation in `update_index`.
- doc_types.yaml lookup: `index_dir` first, fallback to `config_path.parent` (shared vocabulary in cloud sync)
