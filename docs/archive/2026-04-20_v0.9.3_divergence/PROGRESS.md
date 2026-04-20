# PROGRESS — Divergence Detection v0.9.3

**STATUS:** COMPLETED

**Current State:** All 12 steps done. Quality checks green: 364 tests passed, ruff clean, mypy clean. Milestone ready for reinstall + archive.

**Decisions:**
- Divergence is orthogonal to `is_stale`: a card can be both (edited copy needs re-enrichment AND signals group split).
- Flag is carried ONLY by the card whose `content_hash` changed since last reindex. Unchanged former siblings stay clean. Algorithm gates `fresh_drift` computation on `hash_changed` — an unchanged card never acquires a new flag (but a pre-existing flag is narrowed/cleared on every reindex).
- `diverged_from = (previous_flag ∪ fresh_drift) − current_copies − non-existent_doc_ids`. Partial reconvergence narrows; full reconvergence clears.
- Resolution is manual: `accept_divergence(doc_id)` tool for case A (intentional fork) OR natural reconvergence on next reindex for case B (user synced the others).
- Accept does NOT trigger re-enrichment; re-enrichment is handled by the existing `is_stale` / `enrich-index` cycle.
- Embeddings not affected: divergence doesn't change `content_hash`, manifest stays consistent.
- SQLite: `diverged_from` stored as JSON-serialized TEXT, NULL when no divergence. Migration via `contextlib.suppress(sqlite3.OperationalError)` — same pattern as `enriched_content_hash`.
- MCP tools count: 9 → 10 (adding `accept_divergence`).
- Version bump: 0.9.2 → 0.9.3 (minor patch — additive feature, backward-compatible schema).

---

## Progress Events

### E001 — 2026-04-20 13:38 — Plan created, milestone started
Step 0 complete. `docs/PLAN.md` and `docs/PROGRESS.md` created. 12 remaining steps tracked in PLAN.md. Detailed plan lives at `.claude/plans/polymorphic-seeking-waffle.md`.

### E002 — 2026-04-20 13:54 — All steps completed
- Step 1: specs moved to IN_PROGRESS and updated (models/index/server/storage); storage spec schema now also reflects pre-existing `enriched_content_hash` column.
- Step 2: `DocCard.diverged_from`, `CosmosResponse.diverged_documents`, `ProjectSummary.diverged_count` fields added.
- Step 3: SQLite schema + migration + JSON (de)serialization for `diverged_from`.
- Step 4: `ReindexStats.new_divergences` + detection phase in `reindex()`. Caught a design bug during tests — initial version flagged unchanged cards whose siblings had left the group. Fixed by gating fresh_drift computation on `hash_changed` so only the "child of the edit" carries the flag.
- Step 5: `accept_divergence(doc_id)` MCP tool + updates to 4 existing tools (`get_cosmos`, `list_docs`, `get_card`, `reindex_tool`).
- Step 6: web state helper (`accept_divergence`, `count_diverged`, `list_cards(diverged=)`), `POST /api/cards/{doc_id}/accept-divergence` endpoint, templates (status mark in card_list, info block + button in card.html, counter + column in cosmos.html), CSS (`.diverged-mark`, `.diverged-bg`, `.diverged-info`).
- Step 7: test classes `TestDivergenceDetection` (8 scenarios: split/no-false-positive/unique/full-and-partial convergence/cleanup/mode=clean/persistence), `TestAcceptDivergence`, `TestListDocsDivergedFilter`, `TestGetCosmosDivergedCounter`, `TestGetCardDivergenceField`, `TestAcceptDivergenceEndpoint`. Plus SQLite migration + round-trip tests.
- Step 8: ruff check/format green, mypy clean (needed to rename local `old_card`/`merged` to avoid shadowing existing reindex locals), 364 tests pass.
- Step 9: specs → READY.
- Step 10: ARCHITECTURE.md (MCP tools 9→10, Key Decisions entry), CONCEPT.md (new bullet under реализованные фичи + divergence paragraph in reindex section), README.md (Key Features bullet + new row in MCP Tools table, `list_docs` signature updated with `diverged?`).
- Step 11: pyproject.toml 0.9.2 → 0.9.3.
- Step 12: final quality suite green.
