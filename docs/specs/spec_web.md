# Spec: Web UI Module

> Status: READY
> Module: `src/astrolabe/web/`

## Purpose

Local web interface for browsing, searching, and editing astrolabe index cards. Runs as a separate process alongside the MCP server, sharing the same storage backend.

## Architecture

- **Framework**: FastAPI + Jinja2 + HTMX
- **Process**: Independent from MCP server, same `ASTROLABE_CONFIG` env var
- **State**: `AppState` class holds config, merged index, storages, doc_types
- **Rendering**: Server-side HTML (Jinja2 templates), server-side markdown (mistune)
- **Interactivity**: HTMX for partial page updates (no SPA, no JS framework)
- **Styling**: Pico CSS (classless, vendored) + minimal custom CSS

## Module Structure

```
src/astrolabe/web/
├── __init__.py              # Empty
├── __main__.py              # Entry: python -m astrolabe.web
├── app.py                   # FastAPI factory, lifespan, static/templates
├── state.py                 # AppState: config, index, storage, doc_types
├── routes_pages.py          # Full HTML page routes
├── routes_api.py            # HTMX fragment routes
├── templates/               # Jinja2
│   ├── base.html
│   ├── cosmos.html
│   ├── cards.html
│   ├── card.html
│   ├── doc.html
│   ├── search.html
│   └── partials/
│       ├── card_list.html
│       ├── card_fields.html
│       ├── search_results.html
│       └── toast.html
└── static/
    ├── pico.min.css          # Vendored
    ├── htmx.min.js           # Vendored
    └── app.css               # Custom styles
```

## AppState

Extracts state management from `server.py` global pattern into a class:

- `from_config(config_path)` — load config, create storages, merge indexes
- `reload()` — re-read from storage (pick up MCP server changes)
- `save_card(card)` — route to correct storage (shared/private)
- `save_index()` — split and save to both storages
- `get_cosmos()` — build cosmos response (reuses server.py logic)
- `is_desync(card)` — check if file exists on disk

## Routes

### Pages (routes_pages.py)

| Route | Description |
|-------|-------------|
| `GET /` | Dashboard with clickable stats, projects, types |
| `GET /cards` | Card list with query param filters |
| `GET /cards/{doc_id:path}` | Card detail with inline edit |
| `GET /read/{doc_id:path}` | Document viewer (markdown) |
| `GET /search` | Search page |

### API (routes_api.py) — HTML fragments

| Route | Description |
|-------|-------------|
| `GET /api/cards` | Filtered card list partial |
| `GET /api/cards/{id}/edit` | Edit form partial |
| `POST /api/cards/{id}/save` | Save → view partial. Accepts `type`, `summary`, `keywords`, `headings`, `date`. Empty `date` clears it; non-empty `date` must match `YYYY-MM-DD` (validated via `models.DATE_RE`) or a toast error is returned. |
| `POST /api/cards/{id}/cancel` | Cancel → view partial |
| `POST /api/search` | Search results partial |
| `POST /api/reindex` | Reindex action (mode param) |
| `POST /api/refresh` | Reload from storage |

## Dependencies

Optional group `[web]` in pyproject.toml:
- fastapi>=0.115
- uvicorn[standard]>=0.34
- jinja2>=3.1
- mistune>=3.0

## Core Functions Used

- `config.load_config()`, `config.load_doc_types_full()`
- `storage.create_storage()`, `storage.create_storage_at()`
- `index.update_card()`, `index.reindex()`, `index.build_index()`, `index.build_hash_map()`
- `reader.read_file()`
- `search.search()`

## Feature Description

See `docs/WEB_UI.md` for scenarios and UI functions.
