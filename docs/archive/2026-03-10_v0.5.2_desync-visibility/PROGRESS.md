# Progress: Desync visibility — astrolabe-mcp 0.5.2

**STATUS:** COMPLETED

**Current State:** All steps done, tests pass, quality checks clean.

**Decisions:**
- `_is_desync()` helper in server.py to avoid duplication between get_cosmos and list_docs
- `desync_count: int = 0` on ProjectSummary with default for backward compat
- `desync` filter is AND-combined with other filters (independent, not exclusive with stale)
- Pass-through cards (unconfigured projects) are never desync by definition
- Version 0.5.2 (patch, no breaking changes)

---

## Progress Events

### E001 — 2026-03-09 23:49 — Plan created
Feature request discussed, plan approved. Steps 0-7 defined.

### E002 — 2026-03-09 23:57 — All steps completed
Specs updated (spec_models, spec_server), models.py + server.py changed, 6 new tests in TestDesync class, concept.md + README.md updated, version bumped to 0.5.2. All 200 tests pass, ruff/mypy clean.
