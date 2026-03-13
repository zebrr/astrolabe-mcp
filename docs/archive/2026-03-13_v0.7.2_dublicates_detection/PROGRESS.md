# PROGRESS — Content Deduplication v0.7.2

**STATUS:** COMPLETED

**Current State:** All steps done. Quality checks passed (241 tests, ruff, mypy).

**Decisions:**
- Dedup computed on the fly (no storage changes)
- `build_hash_map()` returns only hashes with >1 entry
- search: first result wins, rest deduplicated
- list: `has_copies: true` only when copies exist (field omitted otherwise)
- card: `copies: [doc_id, ...]` computed on the fly (field omitted if no copies)

---

## Progress Events

### E001 — 2026-03-13 14:50 — Plan created
Step 0 complete. PLAN.md and PROGRESS.md created.

### E002 — 2026-03-13 14:54 — All steps completed
- Step 1: `build_hash_map()` added to index.py (4 unit tests)
- Step 2: search_docs dedup by content_hash (3 tests)
- Step 3: list_docs `has_copies` field (2 tests)
- Step 4: get_card `copies` field (2 tests)
- Step 5: specs updated (spec_index.md, spec_server.md)
- Step 6: version bumped to 0.7.2
- Step 7: ARCHITECTURE.md updated
- Quality: ruff ✓, mypy ✓, 241 tests passed
