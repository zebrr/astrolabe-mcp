# Progress: Refactor read_doc/get_doc → v0.2.2

**STATUS:** COMPLETED

## Current State

All 7 steps complete. v0.2.2 released: `get_card` + `read_doc` naming, improved docstrings, 21/21 cards enriched.

## Decisions

- **Naming:** `get_card` (metadata) + `read_doc` (content) — user chose from 3 options
- **Archive untouched:** docs/archive/ contains historical records, not updated
- **Docstring improvements:** added workflow hints, desync/force explanation, /enrich-index recommendation

---

## Progress Events

### E001 — 2026-03-07 22:32 — Steps 1-6 complete

Renamed `read_doc` → `get_card`, `get_doc` → `read_doc` in server.py, tests, and all 14 documentation files. Improved docstrings for all 7 MCP tools. Version bumped to 0.2.2. All 109 tests pass. ruff + mypy clean.

Files changed: server.py, models.py, pyproject.toml, test_server.py, test_models.py, test_index.py, README.md, CLAUDE.md, ARCHITECTURE.md, spec_server.md, CONCEPT.md, settings.local.json, settings.local.example.json, 2x SKILL.md.

### E002 — 2026-03-07 22:36 — Step 7 complete

`/enrich-index` enriched 21/21 cards. Types: spec(6), project_state(6), document(3), reference(2), task(2), instruction(1), skill(1). Index fully searchable.

### E003 — 2026-03-07 22:42 — Step 8 complete (added mid-milestone)

Centralized version to single source: `pyproject.toml` → `importlib.metadata` → `__version__` in `__init__.py`. Removed hardcoded "0.2.2" from models.py, server.py, and 3 test files. Next version bump: change only pyproject.toml + `pip install -e .`. Plan complete.
