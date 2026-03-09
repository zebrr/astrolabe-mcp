# PROGRESS — Private Index + doc_types Refactor (v0.4.0)

## STATUS: COMPLETED

## Current State

All 16 steps complete. v0.4.0 ready.

## Decisions

- **One doc_types.yaml** — shared, in index_dir. Team agrees on types.
- **get_doc_types() tool** — returns full yaml (descriptions + examples) for skill classification.
- **Type validation** — update_index_tool rejects unknown types with clear error.
- **Skill refactor** — remove hardcoded types, use get_doc_types() as source of truth.
- **private_projects dict** — separate from projects for backward compatibility.
- **private_index_dir** — local path, not cloud-synced.
- **Two storages** — shared + private, merged in _index in memory, routing by project flag.
- **get_cosmos unchanged** — still shows type stats from cards with descriptions from yaml.

---

## Progress Events

### E001 — 2026-03-09 12:53 — Step 0: Tracking files created
Created docs/PLAN.md and docs/PROGRESS.md. Plan approved, 16 steps across 3 parts (A: doc_types refactor, B: private index, C: docs + release).

### E002 — 2026-03-09 12:55 — Step 1: Specs updated for doc_types refactor
Updated spec_config.md: added load_doc_types_full() returning full structure (description + examples), made load_doc_types() a wrapper. Updated spec_server.md: added get_doc_types() tool spec, added type validation to update_index_tool, added _doc_types_full to global state, bumped tool count to 8. Both specs → IN_PROGRESS.

### E003 — 2026-03-09 12:55 — Step 2: load_doc_types_full() implemented
Added `load_doc_types_full()` to config.py — returns full structure (description + examples). Refactored `load_doc_types()` as wrapper. All 12 existing tests pass, ruff/mypy clean.

### E004 — 2026-03-09 12:57 — Steps 3-4: get_doc_types() tool + type validation
Added `get_doc_types()` MCP tool returning full vocabulary. Added `_doc_types_full` global, refactored `_load_doc_types` → `_load_all_doc_types()` to load full structure and derive flat `_doc_types`. Added type validation in `update_index_tool()` — rejects unknown types with clear error listing available types. Fixed 4 existing tests that used non-vocabulary types ("project_doc", "doc" → "reference"). All 25 server tests pass.

### E005 — 2026-03-09 13:00 — Step 5: SKILL.md refactored
Removed hardcoded `## Document Types` section. Added `mcp__astrolabe__get_doc_types` to allowed-tools. Workflow now starts with `get_doc_types()` call. Classification rules reference vocabulary from the tool, not hardcoded list. Added note about server-side type validation. Mirrored to `docs/skills_drafts/`. Read skill reference docs for format guidance.

### E006 — 2026-03-09 13:01 — Step 6: Part A complete
All Part A tests added and passing (163 total). New tests: TestLoadDocTypesFull (4 tests), TestGetDocTypes (2 tests), TestTypeValidation (3 tests). Specs → READY. Full quality checks pass (ruff, mypy). Part A (doc_types refactor) is done.

### E007 — 2026-03-09 13:05 — Step 7: Specs updated for private index
Updated three specs for Part B. `spec_models.md` → IN_PROGRESS: AppConfig gets `private_projects`, `private_index_dir`, `all_projects` property, `is_private()` method, two validations (missing dir, key overlap). `spec_storage.md` → IN_PROGRESS: extracted `create_storage_at(index_dir, storage_type)` as core factory, `create_storage(config)` becomes wrapper. `spec_server.md` → IN_PROGRESS: added `_private_storage` global, merge-on-load in startup, `_save_index()` helper for split saves, `_get_storage_for_project()` for single-card routing, `read_doc`/`get_cosmos`/`reindex` use `all_projects`.

### E008 — 2026-03-09 13:06 — Step 8: AppConfig model updated
Added `private_projects: dict[str, Path] = {}`, `private_index_dir: Path | None = None`, `@property all_projects`, `is_private()` method, `@model_validator` with two checks (missing dir, key overlap). All 163 tests pass, ruff/mypy clean. Full backward compat — no existing tests broken.

### E009 — 2026-03-09 13:07 — Step 9: Config loading for private fields
Added `private_index_dir` resolution in `load_config()` — resolved relative to config file directory, same pattern as `index_dir`. All 163 tests pass, ruff/mypy clean.

### E010 — 2026-03-09 13:07 — Step 10: Storage factory refactored
Extracted `create_storage_at(index_dir, storage_type)` as core factory — takes directory and storage type directly. `create_storage(config)` is now a one-line wrapper. All migration logic stays in `create_storage_at`. All 163 tests pass, ruff/mypy clean.

### E011 — 2026-03-09 13:09 — Steps 11-13: Server dual storage implemented
Three steps done together (all in server.py, interdependent):
- **Step 11**: Added `_private_storage` global, `_save_index()` helper (splits docs by privacy, saves to correct storage), `_get_storage_for_project()` helper. `_init()` now creates both storages, loads/merges both indexes, uses `_save_index()`.
- **Step 12**: `get_cosmos()` and `read_doc()` use `config.all_projects`. `update_index_tool()` routes `save_card()` via `_get_storage_for_project()`.
- **Step 13**: `reindex_tool()` recreates both storages, loads/merges from both, uses `config.all_projects` for project lookup and full reindex, calls `_save_index()` for split saves.
All 163 tests pass, ruff/mypy clean. Backward compat maintained — without private config, behavior identical to v0.3.1.

### E012 — 2026-03-09 13:12 — Step 14: Part B tests complete
Added 21 new tests across 4 files (184 total):
- `test_models.py`: TestAppConfigPrivate (4 tests) — all_projects merge, is_private, validation errors, backward compat
- `test_config.py`: TestLoadConfigPrivate (3 tests) — relative private_index_dir resolution, absolute unchanged, backward compat
- `test_storage.py`: TestCreateStorageAt (3 tests) — json/sqlite at custom dirs, two independent storages
- `test_server.py`: TestPrivateIndex (10 tests) — unified index, cosmos shows all, list/search/read private, update routing (private→private_storage, shared→shared_storage), reindex split, single-project reindex, backward compat
Found and fixed bug: `_init()` and `reindex_tool()` used `_config.projects` instead of `all_projects` for scanning — private projects were invisible. Added `_full_scan_config()` helper.
All specs → READY. Full quality checks pass.

### E013 — 2026-03-09 13:14 — Step 15: Documentation updated
- `ARCHITECTURE.md`: 8 tools, private index in key decisions, updated modules table
- `README.md`: added `get_doc_types()` to tools table, type validation note on `update_index_tool`, new "Private Index" section with config example
- `config.example.json`: added `private_projects`, `private_index_dir`, `_private_note`
- CONCEPT.md and CLAUDE.md: no changes needed (CONCEPT.md is read-only, CLAUDE.md Astrolabe MCP Usage section already covers the workflow)

### E014 — 2026-03-09 13:14 — Step 16: v0.4.0 release ready
Version bumped to 0.4.0 in pyproject.toml. Final quality checks: ruff check ✓, ruff format ✓, mypy ✓, 184 tests passing ✓. All 16 steps complete. Plan complete.
