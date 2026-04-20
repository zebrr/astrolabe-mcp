# PLAN — v0.10.0: Optional `date` field for DocCard

Milestone: add optional `date` (YYYY-MM-DD) field to `DocCard` for semantic document dates (statements, receipts, reports). Skill extracts date from content when detectable. Filtering by range and sorting in MCP tools.

See `docs/PROGRESS.md` for events and status.

## Decisions

- Format: strict `YYYY-MM-DD` only. Partial dates (YYYY-MM, YYYY) not stored.
- Date range inside document → take the **end date**.
- API: `date_from` + `date_to` (inclusive) in `list_docs` / `search_docs`.
- Sort param in `list_docs` (`date_desc`, `date_asc`) and `search_docs` (+ `relevance` default).
- `get_cosmos`: add `dated_documents` (global) and `dated_count` (per project).
- `date=None` not emitted in tool responses (pattern like `diverged_from`).
- Cards without `date` excluded from filters; sorted to the end on date sort.

## Steps

- [x] 1. Create `docs/PLAN.md` and `docs/PROGRESS.md` (this file + STATUS tracker).
  - **Input:** Approved plan at `~/.claude/plans/typed-prancing-dove.md`.
  - **Action:** Create both files.
  - **Output:** Tracker files in place.
  - **Checkpoint:** Files exist with correct structure.
  - **Review:** N/A.

- [x] 2. Update specs (status `IN_PROGRESS`): `spec_models.md`, `spec_storage.md`, `spec_search.md`, `spec_server.md`.
  - **Input:** Current specs + decisions above.
  - **Action:** Document `date` field everywhere: model, SQLite column, search filter, tool signatures.
  - **Output:** Specs reflect new API.
  - **Checkpoint:** Specs are consistent with each other.
  - **Review:** User may review after milestone completes.

- [x] 3. `src/astrolabe/models.py`: add `DocCard.date: str | None = None`, `ProjectSummary.dated_count: int = 0`, `CosmosResponse.dated_documents: int = 0`.
  - **Input:** Updated spec_models.md.
  - **Action:** Extend three models.
  - **Output:** Models expose new optional fields.
  - **Checkpoint:** `mypy src/` green; existing tests pass.
  - **Review:** N/A.

- [x] 4. `src/astrolabe/storage_sqlite.py`: add `date TEXT` column, migrate via ALTER, extend `_card_to_row` / `_row_to_card` / `_INSERT_SQL`.
  - **Input:** Updated spec_storage.md, existing migration pattern for `diverged_from`.
  - **Action:** Schema + migration + serialization roundtrip.
  - **Output:** SQLite backend stores `date`.
  - **Checkpoint:** Old DB opens without error; new DB stores and returns `date`.
  - **Review:** N/A.

- [x] 5. `src/astrolabe/index.py`: `update_card` accepts `date`. `reindex` preserves `date` alongside other enrichment fields in stale-preserve and auto-transfer branches.
  - **Input:** Current `update_card` signature + reindex enrichment preserve logic at lines 244-249 and 302-307.
  - **Action:** Add param + preserve date on stale/moved cards.
  - **Output:** `date` behaves as enrichment field end-to-end.
  - **Checkpoint:** Unit tests for `update_card(date=...)` pass.
  - **Review:** N/A.

- [x] 6. `src/astrolabe/search.py`: `search()` and `hybrid_search()` accept `date_from`, `date_to`. Filter is AND with project/type. Sort stays relevance — date sort handled at server layer.
  - **Input:** Existing search with project/type filter pattern.
  - **Action:** Extend filter block; leave scoring untouched.
  - **Output:** Search supports date filter.
  - **Checkpoint:** Unit test: filter inclusive, `date=None` excluded when filter set.
  - **Review:** N/A.

- [x] 7. `src/astrolabe/server.py`:
  - `update_index_tool`: `date` param + regex validation, error dict on bad format
  - `list_docs`: `date_from`, `date_to`, `sort` params, filter + sort + validate formats
  - `search_docs`: same params, `sort="relevance"` default
  - `get_card`: include `date` if non-null
  - `get_cosmos`: count `dated_documents` global + `dated_count` per project
  - All list/search responses: include `date` in card dict only if non-null
  - **Input:** Updated spec_server.md, patterns at `server.py:462-475`, `:853-858`.
  - **Action:** Extend tool signatures, apply filter + sort, format responses.
  - **Checkpoint:** `mypy src/` green; existing tests pass; new tests pass.

- [x] 8. `.claude/skills/enrich-index/SKILL.md` and `docs/skills_drafts/enrich-index/SKILL.md`: new enrichment step — try to extract `date` (full YYYY-MM-DD only, range → end date).
  - **Input:** Current SKILL.md.
  - **Action:** Add bullet to workflow, add section on date extraction, example call.
  - **Output:** Both SKILL.md files synchronized.
  - **Checkpoint:** Files consistent.
  - **Review:** User may validate on real document after merge.

- [x] 9. Tests:
  - `tests/test_models.py` — DocCard/Cosmos extended models
  - `tests/test_index.py` — `update_card(date=...)` round-trip; reindex preserves date on stale; reset on rebuild
  - `tests/test_storage_sqlite.py` — migration from old DB (no date column); save/load roundtrip
  - `tests/test_search.py` — date_from/date_to inclusive; `date=None` excluded
  - `tests/test_server.py` — sort options; cosmos dated counters; update_index_tool rejects bad format
  - **Checkpoint:** `python -m pytest -v` green.

- [x] 11. Web UI: view/edit date in card partial (v0.10.0 extension).
  - **Input:** `src/astrolabe/web/routes_api.py::card_save`, `src/astrolabe/web/state.py::do_update_card`, `src/astrolabe/web/templates/partials/card_fields.html`.
  - **Action:**
    - Extract `DATE_RE` to `src/astrolabe/models.py` (shared constant).
    - Extend `update_card` (`index.py`) and `update_index_tool` (`server.py`) to accept `""` as explicit clear. `None` = untouch. Validator passes through `""`.
    - Web: `state.do_update_card(..., date=...)` accepts the same tri-state. `routes_api.card_save` accepts `date: str = Form("")`, validates non-empty non-match → toast error.
    - Template: view-mode row "Date: YYYY-MM-DD or —". Edit-mode `<input type="date" name="date" value="{{ card.date or '' }}">`.
  - **Tests:** extend `test_index` / `test_server` for clear behavior; extend `test_web` for round-trip (set → clear → invalid→toast).
  - **Checkpoint:** ruff, mypy, pytest green.
  - **Review:** user validates the UI interaction after reinstall.

Updated: 2026-04-20 — step 11 added after E002, reopened milestone.

- [x] 10. Quality checks, version bump, ARCHITECTURE.md, spec status → READY.
  - **Action:** `ruff check src/ tests/`, `ruff format src/ tests/`, `mypy src/`, `python -m pytest -v`. Bump `pyproject.toml` 0.9.3 → 0.10.0. Add Key Technical Decision to ARCHITECTURE.md. Flip specs to READY.
  - **Checkpoint:** All checks green; version in pyproject updated.
  - **Review:** User reviews before commit (commits only on user request).
