# Milestone 4: SQLite Storage Backend (v0.3.0)

Created: 2026-03-08

## Steps

- [x] 0. Create PLAN.md + PROGRESS.md
  - Input: Approved plan document
  - Action: Create tracking files per CLAUDE.md rules
  - Output: docs/PLAN.md, docs/PROGRESS.md
  - Checkpoint: Both files follow format rules
  - Review: N/A (this step creates the tracking files)

- [x] 1. Spec: storage abstraction
  - Input: Design from plan
  - Action: Write `docs/specs/spec_storage.md` (Protocol, JsonStorage, SqliteStorage, migration, factory)
  - Output: spec_storage.md (DRAFT)
  - Checkpoint: Spec covers all public APIs and edge cases
  - Review: Mark done, append event, review remaining steps

- [x] 2. AppConfig: add `storage` field
  - Input: spec_storage.md
  - Action: Add `storage: Literal["json", "sqlite"] = "json"` to AppConfig in models.py. Update spec_models.md.
  - Output: models.py updated, spec_models.md (IN_PROGRESS -> READY)
  - Checkpoint: ruff, mypy, existing tests pass. Default "json" = no breaking changes.
  - Review: Mark done, append event

- [x] 3. StorageBackend Protocol + factory
  - Input: spec_storage.md
  - Action: Create `src/astrolabe/storage.py` with Protocol class and `create_storage()` factory
  - Output: storage.py
  - Checkpoint: mypy passes, factory returns correct type based on config
  - Review: Mark done, append event, update spec_storage.md status -> IN_PROGRESS

- [x] 4. JsonStorage implementation
  - Input: storage.py protocol, existing index.py
  - Action: Create `src/astrolabe/storage_json.py`. Wrap load_index/save_index. save_card = load + update + save.
  - Output: storage_json.py
  - Checkpoint: mypy passes, isinstance check against Protocol
  - Review: Mark done, append event

- [x] 5. SqliteStorage implementation
  - Input: storage.py protocol, schema design
  - Action: Create `src/astrolabe/storage_sqlite.py`. Schema creation, DELETE journal mode, load/save/save_card.
  - Output: storage_sqlite.py
  - Checkpoint: mypy passes, isinstance check against Protocol
  - Review: Mark done, append event

- [x] 6. Migration: JSON -> SQLite
  - Input: Both storage implementations
  - Action: Add migrate_json_to_sqlite() to storage_sqlite.py. Wire into create_storage() factory.
  - Output: Migration logic in factory + storage_sqlite.py
  - Checkpoint: Test migration preserves all cards and enrichment
  - Review: Mark done, append event, update spec if migration design changed

- [x] 7. Server refactor
  - Input: StorageBackend, both implementations
  - Action: Refactor server.py to use _storage global and StorageBackend methods
  - Output: server.py refactored
  - Checkpoint: All existing server tests pass
  - Review: Mark done, append event, update spec_server.md

- [x] 8. Tests
  - Input: All new modules
  - Action: Write tests/test_storage.py — parametrized tests for both backends
  - Output: test_storage.py, all tests green
  - Checkpoint: pytest -v — all pass
  - Review: Mark done, append event, update spec_storage.md -> READY

- [x] 9. Documentation
  - Input: All code changes complete
  - Action: Update ARCHITECTURE.md, README.md, config.example.json, CONCEPT.md (with approval), spec_index.md, spec_server.md
  - Output: All docs current
  - Checkpoint: Docs reflect implementation
  - Review: Mark done, append event

- [x] 10. Version bump + final checks
  - Input: Everything done
  - Action: Bump to 0.3.0. Full quality checks. Smoke test with real index.
  - Output: v0.3.0 ready
  - Checkpoint: ruff, mypy, pytest all green. Manual smoke test.
  - Review: Mark done, PROGRESS status -> COMPLETED, propose CLAUDE.md improvements
