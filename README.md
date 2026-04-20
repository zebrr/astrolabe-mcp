# astrolabe-mcp

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/protocol-MCP-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

A transparent knowledge layer across multiple projects via the Model Context Protocol (MCP). Any agent — Claude Code, Claude Desktop, or any MCP-compatible client — connects and gets unified search and navigation across all your documentation.

> *"The night is still; the desert hearkens unto God, and star speaks unto star"* — Lermontov

## What is this

Astrolabe is a **dumb server + smart agent** architecture. The server only walks files, stores an index, and serves content. All classification, summarization, and keyword extraction happen on the agent side (the LLM you're already paying for). The agent reads a file, understands it, and calls `update_index_tool()` to enrich the index card.

**The problem it solves:** you work on multiple projects with scattered documentation — specs, references, tasks, reports, skills. Knowledge is siloed. Claude Code can't see files outside its current project. There's no single place to ask "do we have a reference for X?" across projects.

**The solution:** one MCP server indexes all your projects. Any agent connects and searches across everything.

## Key Features

- **Git-aware scanning** — uses `git ls-files` to respect `.gitignore` automatically, with rglob fallback for non-git directories
- **Cross-project search** — find documents across all indexed projects from any agent
- **Agent-powered enrichment** — the LLM classifies, summarizes, and tags documents
- **Progressive disclosure** — browse the catalog first, read files only when needed
- **Section extraction** — read specific sections by heading, not the entire file
- **Managed typing** — fixed set of document types with `undef` as a catch-all
- **Binary-safe** — media and office files are indexed by metadata and filename
- **Zero-intrusion** — no frontmatter, no changes to your project files
- **Semantic search** — optional `deep_search` via ChromaDB embeddings, finds documents by meaning even without enrichment
- **Web UI** — local browser interface for browsing, searching, and editing index cards with markdown rendering
- **Divergence tracking** — detects when one copy of a duplicated document is edited while others stay behind, flags the split for manual resolution via `accept_divergence()` or natural reconvergence on the next reindex

## Quick Start

```bash
git clone https://github.com/zebrr/astrolabe-mcp.git
cd astrolabe-mcp
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows
pip install -e .
```

**Optional features** (install any combination):

| Command | What it adds |
|---------|-------------|
| `pip install -e ".[web]"` | Local web UI (FastAPI + Jinja2 + HTMX) |
| `pip install -e ".[embeddings]"` | Semantic search via ChromaDB (`deep_search` tool) |
| `pip install -e ".[dev]"` | Dev tools (ruff, mypy, pytest) |
| `pip install -e ".[web,embeddings]"` | All optional features |
| `pip install -e ".[dev,web,embeddings]"` | Everything |

`pip install -e .` installs only the base: MCP server with keyword search, enrichment, and all core tools. Optional groups add features without breaking the base.

Copy and edit the config files:

```bash
cp runtime/config.example.json runtime/config.json
cp runtime/doc_types.example.yaml runtime/doc_types.yaml
```

Edit `runtime/config.json` — add your project paths (see [Configuration](#configuration)).

Connect to Claude Code or Claude Desktop (see [Connecting to Clients](#connecting-to-clients)).

Done. The server starts automatically when the client launches.

## Configuration

### Projects (`runtime/config.json`)

```json
{
  "projects": {
    "my-project": "/path/to/my-project",
    "api-docs": "/path/to/api-docs",
    "web-app": "/path/to/web-app"
  },
  "index_dir": ".",
  "storage": "json",
  "index_extensions": [
    ".md", ".yaml", ".yml", ".txt", ".py", ".sh",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".mp3", ".wav", ".mp4", ".mov"
  ],
  "ignore_dirs": ["src", "lib", "app", "tests", "test"],
  "ignore_files": ["*.lock"],
  "max_file_size_kb": 50
}
```

**Storage backend:** `"json"` (default) or `"sqlite"`. JSON works out of the box. Switch to SQLite for large indexes (500+ cards) — enrichment writes ~1KB per card instead of rewriting the entire file. Changing the setting auto-migrates the existing JSON index, no re-enrichment needed.

**What gets indexed:** files matching `index_extensions` in project directories. Git-aware scanning uses `git ls-files` to automatically exclude gitignored files (`.venv/`, `node_modules/`, `__pycache__/`, etc.). For non-git directories, falls back to recursive file walking.

**Note:** `ignore_dirs` and `ignore_files` are for **domain-specific exclusions** — git-tracked directories/files you don't want in the knowledge index. For example, `src` excludes source code that git tracks but isn't useful as knowledge documents. Gitignored paths are excluded automatically and don't need to be listed here.

### Document Types (`runtime/doc_types.yaml`)

Defines the vocabulary of document types used during enrichment. The agent uses these descriptions to classify files:

```yaml
document_types:
  instruction:
    description: >
      Project instruction, agent rules and workflow.
  reference:
    description: >
      Reference material on API, tool, approach, or methodology.
  spec:
    description: >
      Technical specification, architecture, design document.
  task:
    description: >
      Work assignment with context, steps, and acceptance criteria.
  # ... see doc_types.example.yaml for the full list
```

Current built-in types: `instruction`, `reference`, `task`, `report`, `spec`, `document`, `skill`, `utility`, `project_state`, `binary_doc`, `media`, `undef`.

## Connecting to Clients

Astrolabe is an MCP server with stdio transport. The client starts the server process automatically — you just tell it how.

### Claude Code

To make astrolabe available **from any project**, add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "astrolabe": {
      "command": "/absolute/path/to/astrolabe-mcp/.venv/bin/python",
      "args": ["-m", "astrolabe.server"],
      "cwd": "/absolute/path/to/astrolabe-mcp",
      "env": {
        "ASTROLABE_CONFIG": "/absolute/path/to/astrolabe-mcp/runtime/config.json"
      }
    }
  }
}
```

Replace `/absolute/path/to/astrolabe-mcp` with the real path. The full path to the venv Python is required.

For a single project only, use `.mcp.json` in that project's root (same format).

### Claude Desktop

Add to `claude_desktop_config.json`:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Same JSON format as above.

### Verify

After adding the config, restart the client. Ask the agent:

> "Call get_cosmos() from astrolabe"

It should return your project list and index statistics.

## How it Works

### Architecture

```
models.py ← config.py ← index.py ← server.py
models.py ← reader.py ←──────────────┘
models.py ← search.py ←──────────────┘
chunker.py ← embeddings.py ←─────────┘  (optional)
                                      ← web/state.py ← web/app.py
```

On startup, the server reads `config.json`, scans all project directories, and builds an index of file metadata (name, path, size, content hash). Index cards start empty — no types, summaries, or keywords.

### Enrichment

The agent enriches cards by reading files and filling in metadata. Here's a typical session:

```
Agent → get_cosmos()
       ← {projects: 3, total: 120, empty: 45, enriched: 75}

Agent → list_docs(stale=true)
       ← {total: 45, limit: 50, offset: 0, result: [{doc_id: "web-app::docs/API.md", ...}, ...]}

Agent → read_doc("web-app::docs/API.md")
       ← {content: "# REST API Reference\n\n## Authentication\n...", total_lines: 340}

Agent → update_index_tool(
          "web-app::docs/API.md",
          type="reference",
          summary="REST API reference: authentication, endpoints, rate limits, error codes.",
          keywords=["api", "rest", "authentication", "rate-limits", "endpoints"]
        )
       ← {status: "updated", enriched_at: "2026-03-06T12:00:00Z"}
```

After enrichment, the card is searchable:

```
Agent → search_docs("authentication api")
       ← {total: 3, max_results: 20, result: [{doc_id: "web-app::docs/API.md", relevance: 0.92, ...}]}
```

An included enrichment skill (`enrich-index`) automates batch enrichment — it processes all stale cards in a forked context. See `.claude/skills/enrich-index/SKILL.md`.

### Search

`search_docs(query)` performs bilingual stem matching (English + Russian) over enriched cards with field weights:

| Field | Weight |
|-------|--------|
| keywords | 3.0 |
| headings | 2.0 |
| summary | 1.5 |
| filename | 0.8 |

Each query token and each word in a field are stemmed with both EN and RU Snowball stemmers. A token matches a word if their stem sets intersect — so "running" finds "run", and "документы" finds "документ". Filenames are split on `_`, `-`, `.` before matching. Results are sorted by relevance score.

### Semantic Search (optional)

`deep_search(query)` performs semantic search over actual file content using ChromaDB embeddings. Unlike `search_docs` which matches keywords on enriched cards, `deep_search` finds documents by meaning — even unenriched ones.

**When to use:** when `search_docs` returns too few results, or when searching for a concept rather than an exact term. The agent is guided automatically — `search_docs` hints at `deep_search` when results are sparse.

**Setup:** add `"embeddings": true` to `config.json` and install with `pip install -e ".[embeddings]"`. Run `reindex_tool()` to build embeddings (one-time, takes ~1-2 minutes for 1500 documents). After that, `deep_search` is available as a separate MCP tool.

**How it works:** files are split into ~800-character chunks and embedded using ChromaDB's built-in model (all-MiniLM-L6-v2, ~80MB, runs locally, no API keys). On query, `deep_search` combines semantic similarity with stem matching for hybrid scoring.

**Storage:** embeddings are stored locally (`runtime/.chromadb/` by default, configurable via `embeddings_dir`). They are **not cloud-synced** — ChromaDB's internal files (HNSW index) are too large for reliable cloud drive sync. Embeddings are rebuilt per machine on first `reindex_tool()` call; subsequent runs only update new/changed documents (tracked via manifest).

## MCP Tools

| Tool | Description |
|------|-------------|
| `get_doc_types()` | Document type vocabulary from doc_types.yaml (descriptions + examples) |
| `get_cosmos()` | Entry point. Projects, document types, index stats |
| `list_docs(project?, type?, stale?, desync?, diverged?, limit?, offset?)` | List document cards with filters and pagination |
| `search_docs(query, project?, type?, max_results?)` | Fast keyword search with relevance ranking |
| `deep_search(query, project?, max_results?)` | Semantic search over file content (requires `embeddings: true`) |
| `get_card(doc_id)` | Index card metadata — type, summary, keywords (no file content) |
| `read_doc(doc_id, section?, range?)` | Read file content — full, by heading, or line range |
| `update_index_tool(doc_id, type?, summary?, keywords?, headings?)` | Enrich a card (type validated against doc_types.yaml) |
| `reindex_tool(project?, mode?)` | Rescan filesystem. `mode`: `update` (default) / `clean` (remove missing) / `rebuild` (reset all) |
| `accept_divergence(doc_id)` | Accept that a previously-duplicated document was intentionally edited out of its group. Clears `diverged_from` flag |

**doc_id format:** `project::rel_path` — e.g., `web-app::docs/API.md`.

**Section reading:** `read_doc("web-app::docs/API.md", section="Authentication")` extracts from that heading to the next heading of the same or higher level. Returns available headings if the section isn't found.

## Cross-Platform Sync

Astrolabe supports sharing a single index across machines (e.g., Windows + Mac) via a cloud folder (Google Drive, OneDrive).

**Setup:** each machine has its own `runtime/config.json` (gitignored) with `index_dir` pointing to the shared cloud folder. Different machines may have different subsets of projects configured.

**How it works:**

- **Hash normalization** — line endings (CRLF/LF) are normalized before hashing, so the same file produces the same hash on any platform
- **Pass-through** — cards from projects not in the local config are preserved during reindex (they belong to another machine's projects)
- **Desync detection** — if a file is missing locally but exists in the index, `get_cosmos()` reports `desync_documents`. Run `reindex()` to update, or `git pull` if files are from another machine
- **Stale detection** — hash-based: if `content_hash` differs from `enriched_content_hash`, the card is stale and needs re-enrichment. Reliable across machines (no timestamp dependency)
- **Shared doc_types** — `doc_types.yaml` is loaded from next to the index file first, then next to the config file. When using a cloud index, place `doc_types.yaml` in the same cloud folder to share document type definitions across machines
- **Reindex modes** — `reindex_tool(mode="clean")` removes cards for deleted/moved files while preserving enrichment. `reindex_tool(mode="rebuild")` resets all enrichment (nuclear option). Pass-through cards from other machines are always preserved

## Private Index

Some projects shouldn't be visible in the shared cloud index (personal notes, private repos). Astrolabe supports a separate private storage alongside the shared one.

Add to `runtime/config.json`:

```json
{
  "projects": {
    "shared-project": "/path/to/shared"
  },
  "private_projects": {
    "my-notes": "/path/to/my-notes"
  },
  "private_index_dir": "../private-index"
}
```

**How it works:**
- `private_projects` are indexed separately in `private_index_dir` (local, not cloud-synced)
- The server merges both indexes in memory — all tools work transparently across shared and private documents
- `update_index_tool()` routes saves to the correct storage based on project
- `reindex_tool()` splits results to the correct storage
- One shared `doc_types.yaml` — the team agrees on types, private projects use the same vocabulary
- Without `private_projects`/`private_index_dir`, behavior is identical to before

## Web UI

Astrolabe includes an optional local web interface for browsing and managing the index in a browser.

**Install and run:**

```bash
pip install -e ".[web]"
.venv/bin/python -m astrolabe.web          # macOS/Linux
# .venv\Scripts\python -m astrolabe.web    # Windows
```

Opens at http://127.0.0.1:8420. Custom host/port: `--host 0.0.0.0 --port 9000`.

**Features:**

- **Dashboard** — index health overview, project stats, document type breakdown. All elements are clickable links to filtered card lists
- **Card list** — filterable by project, type, stale/empty/desync. Filters auto-apply on change
- **Card editing** — inline editing of type, summary, keywords, and headings. Changes are persisted to the same storage the MCP server uses
- **Document reader** — markdown rendering with section navigation
- **Search** — live search from the header, results ranked by relevance
- **Reindex** — trigger reindex (update/clean/rebuild) from the header

The web server runs as a separate process and shares the storage backend with the MCP server. Changes made in the web UI are immediately visible to MCP clients, and vice versa (click Refresh to reload).

## Current Limitations

- **Binary files** — PDF, Office documents are indexed by filename only (no content extraction yet)
- **Media files** — images, audio, video indexed by filename only
- **No code parsing** — `.py`/`.sh` files are read as plain text, no AST analysis
- **Semantic search model** — fixed to all-MiniLM-L6-v2, no model choice yet
- **Embeddings are local** — not synced via cloud drives (ChromaDB HNSW files are too large); rebuilt per machine on first reindex
- **No file writing** — index card editing via Web UI, but no document content editing via MCP
- **Single index file** — JSON uses filelock, SQLite uses its own locking; not designed for high-throughput multi-client scenarios

## Contributing

Fork, install with `pip install -e ".[dev,web,embeddings]"`, run `ruff check src/ tests/ && mypy src/ && pytest -v` before submitting.

## License

MIT License

Copyright (c) 2025 Askold Romanov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
