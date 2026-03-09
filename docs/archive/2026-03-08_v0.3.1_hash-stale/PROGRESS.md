# PROGRESS — Hash-based stale detection (v0.3.1)

**STATUS:** COMPLETED

## Current State

All steps complete. Server restart needed for live verification.

## Decisions

- **Hash over timestamps:** `is_stale` now uses `content_hash != enriched_content_hash` instead of `modified > enriched_at`. Timestamps remain for display only.
- **Desync = missing files only:** Both reindex and get_cosmos define desync as "file in index but not on disk". The "informational desync" (enriched_at > modified) was a bug — it flagged normal state after enrichment.
- **Migration:** Existing enriched cards without `enriched_content_hash` get it auto-set to `content_hash` during reindex (hash matches = enrichment valid).
- **get_cosmos keeps exists():** Cheap disk check stays as early desync detection without needing reindex.

---

## Progress Events

### E001 — 2026-03-08 22:04 — Plan created

Analysis of stale/desync bugs: two contradicting mechanisms (hash in reindex, timestamps in get_cosmos/is_stale), false "informational desync" counting 1002 normal cards. Designed hash-based solution with `enriched_content_hash` field.

### E002 — 2026-03-08 22:10 — All steps completed

Steps 1-6 done: specs updated, models.py (enriched_content_hash + hash-based is_stale), index.py (removed informational desync, added migration, update_card saves enriched_content_hash), server.py (stale flag in get_card, docstrings), tests (154 passed), docs (ARCHITECTURE, README), version bumped to 0.3.1. Step 7 (live verification): server needs restart to pick up code changes — old process still runs v0.3.0.
