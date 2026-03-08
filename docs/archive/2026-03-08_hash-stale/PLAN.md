# PLAN — Hash-based stale detection (v0.3.1)

## Goal

Replace timestamp-based stale detection with content_hash comparison. Fix false desync reporting in reindex.

## Steps

- [x] 1. **Specs first:** Update spec_models.md, spec_index.md, spec_server.md
  - Input: Current specs, plan
  - Action: Add `enriched_content_hash` field, change `is_stale` definition, update desync semantics
  - Output: All three specs reflect new design
  - Checkpoint: Specs consistent with each other
  - Review: No contradictions between specs

- [x] 2. **models.py:** Add `enriched_content_hash`, change `is_stale`
  - Input: spec_models.md (updated)
  - Action: Add field, rewrite `is_stale` property to use hash comparison
  - Output: DocCard with hash-based stale detection
  - Checkpoint: `ruff check`, `mypy`
  - Review: `is_empty` still works (checks `enriched_at is None`)

- [x] 3. **index.py:** Fix `update_card()` and `reindex()`
  - Input: spec_index.md (updated)
  - Action: (a) `update_card` saves `enriched_content_hash = content_hash`, (b) remove informational desync check (lines 204-206), (c) migration: unchanged enriched cards without `enriched_content_hash` get it set to `content_hash`, (d) stale path in reindex: copy `enriched_content_hash` from old card
  - Output: Clean reindex stats, hash-based enrichment tracking
  - Checkpoint: `ruff check`, `mypy`
  - Review: desync only counts missing files

- [x] 4. **server.py:** Update `get_card()` response and docstrings
  - Input: spec_server.md (updated)
  - Action: (a) Add `"stale": card.is_stale` to get_card response, (b) update get_cosmos docstring, (c) update reindex_tool docstring
  - Output: Agents see stale flag directly
  - Checkpoint: `ruff check`, `mypy`
  - Review: get_cosmos exists() check stays

- [x] 5. **Tests:** Update test_models.py, test_index.py, test_server.py
  - Input: New behavior specs
  - Action: (a) Fix is_stale tests to use hash comparison, (b) Remove/rewrite TestDesync.test_enriched_at_greater_than_modified_is_desync, (c) Add hash-based stale tests, (d) Add migration test, (e) Add get_card stale flag test
  - Output: All tests pass
  - Checkpoint: `pytest -v` green
  - Review: No test relies on timestamp-based stale detection

- [x] 6. **Docs & version:** Update ARCHITECTURE.md, bump pyproject.toml
  - Input: Completed changes
  - Action: Update key technical decisions, bump version to 0.3.1
  - Output: Docs reflect new reality
  - Checkpoint: Quality checks pass
  - Review: README.md cross-platform section still accurate

- [x] 7. **Live verification:** Test with real index via MCP tools
  - Input: Running server
  - Action: reindex → confirm desync=0, edit file → reindex → confirm stale=1, enrich → confirm stale=0, get_card → confirm stale flag present
  - Output: All scenarios work
  - Checkpoint: Manual verification
  - Review: No false desync
