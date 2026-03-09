# Plan: Refactor read_doc/get_doc + Improve Tool Descriptions → v0.2.2

- [x] 1. Rename `read_doc()` → `get_card()`, `get_doc()` → `read_doc()` in server.py
  - Input: confusing names
  - Action: rename functions, update docstrings
  - Output: intuitive names — `get_card` = metadata, `read_doc` = file content
  - Checkpoint: code compiles

- [x] 2. Improve docstrings for all 7 MCP tools
  - Input: bare descriptions
  - Action: add workflow hints, desync/force/pass-through explanations, type examples
  - Output: agents get better context from tool descriptions
  - Checkpoint: docstrings updated

- [x] 3. Update tests — rename test classes and method calls
  - Input: tests reference old function names
  - Action: `TestReadDoc` → `TestGetCard`, `TestGetDoc` → `TestReadDoc`, fix all calls
  - Output: tests pass with new names
  - Checkpoint: pytest green

- [x] 4. Version bump 0.2.1 → 0.2.2
  - Input: pyproject.toml, models.py, server.py, test assertions
  - Action: update version strings everywhere
  - Output: consistent 0.2.2
  - Checkpoint: all version assertions pass

- [x] 5. Update documentation — README, CLAUDE.md, ARCHITECTURE, specs, CONCEPT, settings, skills
  - Input: 14 files with old tool names
  - Action: rename all references
  - Output: docs consistent with code
  - Checkpoint: grep for `get_doc` / old `read_doc` references → none remain

- [x] 6. Quality checks
  - Input: all changes done
  - Action: ruff check + format, mypy, pytest
  - Output: all green
  - Checkpoint: 109 tests pass, 0 warnings

- [x] 7. Run `/enrich-index` for all stale/empty cards
  - Input: 19 cards need enrichment after force reindex
  - Action: `/enrich-index` skill
  - Output: all cards enriched
  - Checkpoint: `get_cosmos()` shows `empty_documents: 0`

- [x] 8. Centralize version — single source of truth in pyproject.toml
  - Input: version hardcoded in 6 places
  - Action: `importlib.metadata.version()` в `__init__.py`, импорт в код и тесты
  - Output: version defined only in pyproject.toml
  - Checkpoint: 109 tests pass, `__version__` == "0.2.2"
  - Added: 2026-03-07 — user noticed 6 places is too many
