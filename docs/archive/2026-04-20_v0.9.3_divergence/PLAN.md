# PLAN — Divergence Detection v0.9.3

Feature: детекция расщепления группы дублей при редактировании одного из экземпляров. Divergence — отдельная ось состояния карточки, ортогональная `is_stale`. Полное описание: `/Users/askold.romanov/.claude/plans/polymorphic-seeking-waffle.md`.

- [x] **Step 0**: Create `docs/PLAN.md` + `docs/PROGRESS.md` (STATUS=IN_PROGRESS)
- [x] **Step 1**: Specs → IN_PROGRESS + updated content (`spec_models.md`, `spec_index.md`, `spec_server.md`, `spec_storage.md`)
- [x] **Step 2**: `models.py` — `DocCard.diverged_from`, `CosmosResponse.diverged_documents`, `ProjectSummary.diverged_count`
- [x] **Step 3**: `storage_sqlite.py` — `diverged_from TEXT` column, migration, JSON (de)serialization
- [x] **Step 4**: `index.py` — `ReindexStats.new_divergences` + detection phase in `reindex()` (diff old/new hash_map, set/narrow/clear flag)
- [x] **Step 5**: `server.py` — new `accept_divergence(doc_id)` tool + updates to `get_cosmos`, `list_docs`, `get_card`, `reindex_tool`
- [x] **Step 6**: `web/` — state helper, `POST /api/cards/{doc_id}/accept-divergence` endpoint, templates (card_list, card, cosmos)
- [x] **Step 7**: Tests — `test_index.py`, `test_server.py`, `test_storage.py`, `test_web.py`
- [x] **Step 8**: Quality checks — `ruff check`, `ruff format`, `mypy`, `pytest -v`
- [x] **Step 9**: Specs → READY
- [x] **Step 10**: Docs — `ARCHITECTURE.md`, `CONCEPT.md`, `README.md`
- [x] **Step 11**: Version bump `pyproject.toml` → `0.9.3`
- [x] **Step 12**: Final checks + reinstall reminder to user
