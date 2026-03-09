# Plan: Git-aware scanning — astrolabe-mcp 0.6.0

## Goal

Replace `rglob("*")` in `scan_project()` with `git ls-files` as primary file source. Eliminates phantom desync from gitignored files on multi-machine setups. Fallback to `rglob("*")` for non-git directories.

## Steps

- [x] 0. Archive v0.5.2 PLAN.md + PROGRESS.md, create new PLAN.md + PROGRESS.md
- [x] 1. Update spec: `docs/specs/spec_index.md` → IN_PROGRESS
- [x] 2. Implement git-aware scanning in `src/astrolabe/index.py`
- [x] 3. Clean up config examples: `runtime/config.example.json`
- [x] 4. Add tests in `tests/test_index.py` + `tests/conftest.py`
- [x] 5. Quality checks (ruff, mypy, pytest)
- [x] 6. Finalize spec: `docs/specs/spec_index.md` → READY
- [x] 7. Update docs: ARCHITECTURE.md, README.md, CONCEPT.md
- [x] 8. Version bump: pyproject.toml 0.5.2 → 0.6.0
- [x] 9. Final quality checks + close plan
