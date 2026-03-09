# PLAN — Private Index + doc_types Refactor (v0.4.0)

## Goal

Two bundled changes: (A) Make doc_types.yaml the real source of truth — new `get_doc_types()` tool, type validation in `update_index_tool`, skill refactor. (B) Private index — separate storage for private projects, merged transparently in memory.

## Steps

### PART A: doc_types refactor

- [x] 1. **Specs:** Update spec_config.md, spec_server.md for doc_types changes
  - Input: Current specs
  - Action: Add `load_doc_types_full()` spec, add `get_doc_types()` tool spec, add type validation to `update_index_tool()` spec
  - Output: Specs IN_PROGRESS
  - Checkpoint: Specs cover all new behaviors

- [x] 2. **config.py:** Implement `load_doc_types_full()`
  - Input: spec_config.md
  - Action: New function returning full structure (description + examples). Refactor `load_doc_types()` as wrapper.
  - Output: config.py updated
  - Checkpoint: ruff, mypy, tests

- [x] 3. **server.py:** New `get_doc_types()` MCP tool
  - Input: spec_server.md, config.py
  - Action: Add `_doc_types_full` global, load in `_init()` and `reindex_tool()`, derive `_doc_types` from it, new tool returns full vocabulary
  - Output: server.py with new tool
  - Checkpoint: ruff, mypy, test

- [x] 4. **server.py:** Type validation in `update_index_tool()`
  - Input: spec_server.md
  - Action: Validate type against `_doc_types` keys, return clear error with available types list
  - Output: server.py updated
  - Checkpoint: ruff, mypy, validation tests

- [x] 5. **SKILL.md:** Refactor enrich-index skill
  - Input: Current SKILL.md, skill reference docs
  - Action: Remove hardcoded Document Types section, add `get_doc_types()` to workflow and allowed-tools, mirror to skills_drafts
  - Output: Both SKILL.md updated
  - Checkpoint: Instructions coherent

- [x] 6. **Tests:** Part A test suite
  - Input: All Part A code
  - Action: test_config (load_doc_types_full), test_server (get_doc_types, type validation)
  - Output: All tests green, specs → READY
  - Checkpoint: pytest -v

### PART B: Private Index

- [x] 7. **Specs:** Update spec_models.md, spec_storage.md, spec_server.md for private index
  - Input: Current specs
  - Action: Add private_projects, private_index_dir, all_projects, is_private, create_storage_at, _private_storage, merge-on-load, save routing, reindex split
  - Output: Specs IN_PROGRESS
  - Checkpoint: Specs cover all new behaviors

- [x] 8. **models.py:** AppConfig update
  - Input: spec_models.md
  - Action: Add private_projects, private_index_dir, all_projects property, is_private() method, validations
  - Output: models.py updated
  - Checkpoint: ruff, mypy, backward compat

- [x] 9. **config.py:** Private fields loading
  - Input: spec_config.md, models.py
  - Action: Resolve private_index_dir relative to config dir
  - Output: config.py updated
  - Checkpoint: ruff, mypy, test

- [x] 10. **storage.py:** Factory refactor
  - Input: spec_storage.md
  - Action: Extract `create_storage_at(index_dir, storage_type)`, make `create_storage(config)` a wrapper
  - Output: storage.py updated
  - Checkpoint: ruff, mypy, existing tests pass

- [x] 11. **server.py:** Two storages + merge on load
  - Input: spec_server.md, storage.py
  - Action: Add _private_storage, load + merge both indexes in _init(), add _save_index() helper
  - Output: server.py with dual storage
  - Checkpoint: ruff, mypy, starts with and without private config

- [x] 12. **server.py:** Save routing + tool updates
  - Input: server.py with dual storage
  - Action: Route save_card by project privacy, use all_projects in read_doc/get_cosmos
  - Output: server.py updated
  - Checkpoint: ruff, mypy

- [x] 13. **server.py:** Reindex with split
  - Input: server.py
  - Action: Split reindex by shared/private, route saves, handle single-project reindex
  - Output: server.py reindex updated
  - Checkpoint: ruff, mypy

- [x] 14. **Tests:** Part B test suite
  - Input: All Part B code
  - Action: test_models, test_config, test_storage, test_server (dual storage, routing, reindex, backward compat)
  - Output: All tests green, specs → READY
  - Checkpoint: pytest -v

### PART C: Documentation + Release

- [x] 15. **Docs:** Update all documentation
  - Input: All code complete
  - Action: ARCHITECTURE.md, README.md, config.example.json, CONCEPT.md (with approval), CLAUDE.md (with approval)
  - Output: All docs current
  - Checkpoint: Docs reflect implementation

- [x] 16. **Release:** Version bump + final checks
  - Input: Everything done
  - Action: Bump to 0.4.0, ruff, mypy, pytest, smoke test
  - Output: v0.4.0 ready
  - Checkpoint: All checks green
