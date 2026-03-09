# Plan: Desync visibility — astrolabe-mcp 0.5.2

## Goal

Per-project desync count in `get_cosmos()` + `desync` filter in `list_docs()`.

## Steps

- [x] 0. Create PLAN.md + PROGRESS.md
- [x] 1. Update specs: spec_models.md (ProjectSummary.desync_count), spec_server.md (desync filter, _is_desync, per-project desync)
- [x] 2. Code: models.py — add `desync_count: int = 0` to ProjectSummary
- [x] 3. Code: server.py — add `_is_desync()` helper, update `get_cosmos()`, update `list_docs()`
- [x] 4. Tests: test_models.py + test_server.py (TestDesync class)
- [x] 5. Docs: concept.md, README.md, tool docstrings
- [x] 6. Version bump: pyproject.toml 0.5.1 → 0.5.2
- [x] 7. Quality checks + verification
