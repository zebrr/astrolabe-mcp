# Plan: Tool Output Optimization — astrolabe-mcp 0.7.0

## Goal

Reduce MCP tool output size to stay within client token limits (25K). Six changes: pagination for list_docs, top-K for search_docs, adaptive hints on truncation, reduce max_file_size_kb default, strip timestamps from list/search output, proactive agent guidance in tool docstrings.

Source: docs/ASTROLABE_AUDIT.md

## Key Design Decisions

- **Envelope response** for list_docs and search_docs (dict with total, limit/max_results, result, optional hint)
- **search.py unchanged** — max_results handled in server.py only
- **Defaults in config** — `default_list_limit: 50`, `default_search_limit: 20` in AppConfig, not hardcoded

**After EVERY step (mandatory, per CLAUDE.md Code Change Pipeline):**
1. Mark step done in PLAN.md, review remaining steps — still relevant? Need update/split/remove?
2. Append event to PROGRESS.md with real timestamp (`date "+%Y-%m-%d %H:%M"`). Update Status/Current State/Decisions above `---` if changed.
3. Update docs if affected by step: ARCHITECTURE.md, README.md, specs.

## Steps

0. [x] **Create docs/PLAN.md + docs/PROGRESS.md**
   - Input: Approved plan, ASTROLABE_AUDIT.md decisions
   - Action: Create docs/PLAN.md and docs/PROGRESS.md
   - Output: Both files exist
   - Checkpoint: Structure matches CLAUDE.md conventions
   - Review: Step numbering correct, all 6 changes covered

1. [x] **Update specs → status IN_PROGRESS**
   - Input: docs/specs/spec_server.md, docs/specs/spec_reader.md, docs/specs/spec_models.md (all READY)
   - Action: In spec_models.md add `default_list_limit`, `default_search_limit` to AppConfig. In spec_server.md add limit/offset to list_docs, max_results to search_docs, envelope response format, hint templates (from audit), timestamp stripping, docstring guidance notes. In spec_reader.md add available_sections on truncation. Set all three to IN_PROGRESS. spec_search.md unchanged.
   - Output: Three specs updated with status IN_PROGRESS
   - Checkpoint: All new behaviors documented before code
   - Review: Specs cover all 6 accepted changes, hint design matches audit

2. [x] **reader.py: available_sections on truncation**
   - Input: spec_reader.md (updated), src/astrolabe/reader.py line 139
   - Action: In read_file() truncation branch, call `extract_headings(text)` on the full text (already in memory) and set `available_sections` on ReadResult
   - Output: reader.py returns headings list when file is truncated
   - Checkpoint: `ruff check src/ && mypy src/`
   - Review: Full text is available at that point, no extra I/O

3. [x] **Tests: reader truncation with sections**
   - Input: Updated reader.py
   - Action: In tests/test_reader.py add tests for truncation with headings present and absent
   - Output: tests/test_reader.py with new test methods
   - Checkpoint: `pytest tests/test_reader.py -v`
   - Review: Edge case coverage — headings present vs absent

4. [x] **models.py: add config fields for output limits**
   - Input: spec_models.md (updated), src/astrolabe/models.py AppConfig class
   - Action: Add `default_list_limit: int = 50`, `default_search_limit: int = 20` to AppConfig
   - Output: AppConfig has new fields with defaults
   - Checkpoint: `mypy src/`
   - Review: Backwards compatible — existing configs get defaults via Pydantic

5. [x] **server.py: list_docs refactor with pagination, envelope, hints, timestamp stripping**
   - Input: spec_server.md (updated), src/astrolabe/server.py lines 255-299
   - Action: Add limit/offset params, envelope response, adaptive hints, strip timestamps
   - Output: list_docs returns dict envelope with optional hint
   - Checkpoint: `ruff check src/ && mypy src/`
   - Review: Hint adapts to applied filters, counts are from full filtered set

6. [x] **server.py: search_docs refactor with max_results and envelope**
   - Input: spec_server.md (updated), src/astrolabe/server.py lines 302-320
   - Action: Add max_results param, envelope response, hint on truncation
   - Output: search_docs returns dict envelope with optional hint
   - Checkpoint: `ruff check src/ && mypy src/`
   - Review: search.py untouched, slicing in server only

7. [x] **server.py: read_doc enhanced hint on truncation**
   - Input: spec_server.md (updated), reader.py provides available_sections on truncation
   - Action: Replace warning with richer hint including sections list
   - Output: read_doc truncation response includes sections list in hint
   - Checkpoint: `ruff check src/ && mypy src/`
   - Review: Hint only built when truncated, sections from ReadResult

8. [x] **server.py: proactive agent guidance in tool docstrings**
   - Input: Current tool docstrings in server.py
   - Action: Enhance docstrings for all tools with usage tips
   - Output: All 8 tool docstrings enhanced with guidance
   - Checkpoint: Review docstrings read naturally
   - Review: Tips are concise, not bloating the schema

9. [x] **Tests: server envelope responses and new parameters**
   - Input: All server.py changes from steps 5-8
   - Action: Migrate existing tests to envelope format, add new tests for pagination/limits/hints
   - Output: All tests green with envelope format
   - Checkpoint: `pytest -v`
   - Review: Existing test coverage preserved, new edge cases covered

10. [x] **Config template and enrich-index skill updates**
    - Input: runtime/config.example.json, both SKILL.md copies
    - Action: Update config template (max_file_size_kb 50, add limit fields). Update skill for envelope response and pagination.
    - Output: Config template and skill instructions updated
    - Checkpoint: JSON valid, skill instructions coherent
    - Review: Skill handles both small and large stale sets

11. [x] **Finalize: specs READY, docs, version bump, quality checks**
    - Input: All code and tests complete
    - Action: Specs → READY, update ARCHITECTURE.md, README.md, bump to 0.7.0, append to ASTROLABE_AUDIT.md
    - Output: All specs READY, docs current, version bumped
    - Checkpoint: `ruff check src/ tests/ && ruff format src/ tests/ && mypy src/ && pytest -v`
    - Review: Everything consistent, ready for release
