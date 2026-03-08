# Milestone 4: SQLite Storage Backend (v0.3.0)

## STATUS: COMPLETED

## Current State

All 11 steps complete. v0.3.0 ready.

## Decisions

- **Storage abstraction**: Protocol class (not ABC) — fits project's type hint style, structural typing
- **SQLite journal mode**: DELETE (not WAL) — safe for cloud drives (Google Drive), single .db file
- **FTS5**: Deferred to future milestone — no Russian morphology out of the box
- **In-memory index**: Server keeps _index in memory for reads; SQLite optimizes writes only (Level 1)
- **Migration**: Auto-detect on startup — if config says sqlite but only JSON exists, migrate automatically
- **Version**: 0.3.0 (new feature, not breaking change)
- **Config field**: `storage: "json" | "sqlite"`, default "json" for backward compat

---

## Progress Events

### E001 — 2026-03-08 16:36 — Step 0: PLAN.md + PROGRESS.md created
- Created docs/PLAN.md with 11 steps (0-10)
- Created docs/PROGRESS.md with decisions from planning session
- Plan approved by user after design review

### E002 — 2026-03-08 16:45 — Step 1: spec_storage.md written
- Created docs/specs/spec_storage.md (DRAFT)
- Covers: StorageBackend Protocol, JsonStorage, SqliteStorage, factory, migration, schema, error handling
- Remaining steps reviewed — all still relevant

### E003 — 2026-03-08 16:45 — Step 2: AppConfig storage field added
- Added `storage: Literal["json", "sqlite"] = "json"` to AppConfig
- Updated spec_models.md with storage field docs
- All 16 model tests pass, ruff + mypy clean

### E004 — 2026-03-08 16:47 — Steps 3-5: Storage layer implemented
- Created `src/astrolabe/storage.py` — Protocol + create_storage() factory with auto-migration
- Created `src/astrolabe/storage_json.py` — JsonStorage wrapping load_index/save_index
- Created `src/astrolabe/storage_sqlite.py` — SqliteStorage with DELETE journal mode, JSON-serialized list fields
- Both backends pass isinstance(x, StorageBackend) check
- ruff + mypy clean across all 3 modules
- Migration logic built into create_storage() factory (Step 6 partially done)

### E005 — 2026-03-08 16:50 — Step 6: Migration complete
- Migration logic in create_storage() factory — auto-detects JSON→SQLite on startup
- JSON file preserved as backup after migration

### E006 — 2026-03-08 16:50 — Step 7: Server refactored
- Added `_storage: StorageBackend | None = None` global
- `_init()` uses `create_storage(config)` instead of direct load_index/save_index
- `update_index_tool()` uses `_storage.save_card()` — single-row upsert for SQLite
- `reindex_tool()` recreates storage on config reload, uses `_storage.save()`
- Extracted `_load_doc_types()` helper to avoid duplication
- Removed `load_index`/`save_index` imports from server.py
- All 112 tests pass, ruff + mypy clean

### E007 — 2026-03-08 16:52 — Step 8: Storage tests written
- Created tests/test_storage.py — 33 parametrized tests
- Covers: protocol compliance, load/save roundtrip, save_card, exists, path, factory, auto-migration, SQLite-specific
- Full suite: 145 tests pass, ruff + mypy clean

### E008 — 2026-03-08 16:53 — Step 9: Documentation updated
- ARCHITECTURE.md: added storage modules, updated dependency graph, key decisions
- README.md: added `storage` field to config example, storage backend description
- config.example.json: added `storage` and `_storage_note` fields
- spec_storage.md: status DRAFT → READY
- spec_server.md: updated startup sequence, update_index, reindex, added Global State section
- spec_index.md: added note about JsonStorage usage
- Skipped CONCEPT.md update (will ask user)

### E009 — 2026-03-08 16:54 — Step 10: Version bump + final checks
- Bumped version to 0.3.0 in pyproject.toml
- Reinstalled package, verified `__version__ == "0.3.0"`
- Full quality checks: ruff check, ruff format, mypy — all clean
- 145 tests pass (112 existing + 33 new storage tests)
- Milestone complete
