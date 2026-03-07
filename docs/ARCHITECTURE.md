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
│   └── server.py            # MCP transport: tools → core
└── tests/                   # pytest, tmp_path fixtures
```

## Modules

| Module | Status | Spec | Purpose |
|--------|--------|------|---------|
| models.py | done | spec_models.md | Data contracts: AppConfig, DocCard, IndexData, SearchResult, CosmosResponse |
| config.py | done | spec_config.md | Load config.json + doc_types.yaml, skip missing paths |
| index.py | done | spec_index.md | Core: scan projects, build/load/save index, hash, stale detection |
| reader.py | done | spec_reader.md | Read files: full, by section heading, by line range |
| search.py | done | spec_search.md | Token matching with field weights over enriched cards |
| server.py | done | spec_server.md | 7 MCP tools wrapping core functions |

## Dependencies

```
models.py ← config.py ← index.py ← server.py
models.py ← reader.py ←───────────┘
models.py ← search.py ←───────────┘
```

## MCP Tools (7)

`get_cosmos`, `list_docs`, `search_docs`, `get_card`, `read_doc`, `update_index`, `reindex`

See `docs/CONCEPT.md` for full tool specifications.

## Key Technical Decisions

- Index stored as JSON (`.doc-index.json`), `filelock` for concurrent access
- `ignore_dirs` / `ignore_files` fully configurable in config.json
- Content hash: MD5 with CRLF→LF normalization for cross-platform consistency
- Search: token-level matching with field weights (keywords 3.0, filename 2.5, headings 2.0, summary 1.0)
- Cross-platform: pathlib everywhere, rel_path as POSIX strings
- Shared index: pass-through for foreign project cards, desync detection for missing files
- Force reindex: `reindex(force=True)` resets enrichment, respects pass-through
