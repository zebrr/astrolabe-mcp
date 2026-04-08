# PROGRESS — Astrolabe ChromaDB Semantic Search v0.9.0

**STATUS**: IN_PROGRESS

**Current State**: All 15 steps complete. 323 tests pass, ruff/mypy clean. deep_search as separate tool, search_docs restored to pure stemming.

**Decisions**:
- ChromaDB files: `.chromadb/` subdirectory inside index_dir (and private_index_dir)
- Hybrid search weights: constants in search.py (STEM_WEIGHT=0.55, EMBED_WEIGHT=0.45), not configurable in config
- Optional dep group: `[embeddings]` in pyproject.toml
- Missing chromadb package: warning + fallback to stem-only search (server doesn't crash)
- Config: `"embeddings": true/false` (default: false)
- Lazy init: ChromaDB client + model loaded on first use, not at server startup
- Score normalization: fixed STEM_NORMALIZER=8.0 constant (not per-query max)
- Chunk aggregation: max chunk score + 0.2x attenuated extras
- Embedding distance threshold: 1.4 (similarity < 0.3 is noise)
- Inspired by MemPalace project (github.com/milla-jovovich/mempalace) — local ChromaDB with built-in embeddings, zero API cost

---

## Progress Events

### E001 — 2026-04-07 23:21 — Step 0: Project setup
- Created `docs/PLAN.md` + `docs/PROGRESS.md`
- Created `docs/ChromaDB.md` — full architecture doc with design decisions, scoring algorithm, storage layout, performance estimates
- Created `docs/specs/spec_chunker.md` (DRAFT) — chunk_file() API, paragraph-aware splitting, edge cases
- Created `docs/specs/spec_embeddings.md` (DRAFT) — EmbeddingBackend Protocol, ChromaDB implementation, factory pattern

### E002 — 2026-04-07 23:30 — Step 1: chunker.py + tests
- Created `src/astrolabe/chunker.py` — chunk_text() and chunk_file(), paragraph-aware splitting with sentence and hard-split fallbacks
- Created `tests/test_chunker.py` — 18 tests: empty/short/binary/oversized files, overlap, UTF-8, boundary conditions
- All 18 tests pass, ruff clean, mypy clean
- Updated spec_chunker.md → READY

### E003 — 2026-04-07 23:31 — Step 2: models.py changes
- AppConfig: added `embeddings: bool = False`
- CosmosResponse: added `embeddings_enabled: bool = False`, `embedded_chunks: int = 0`
- All 285 tests pass, mypy clean. No breaking changes (all fields have defaults)

### E004 — 2026-04-07 23:51 — Step 3: embeddings.py + embeddings_chroma.py
- Created `src/astrolabe/embeddings.py` — EmbeddingBackend Protocol, EmbeddingResult dataclass, factory, is_embeddings_available()
- Created `src/astrolabe/embeddings_chroma.py` — ChromaEmbeddingBackend with lazy PersistentClient, cosine space, chunk ID scheme, project filtering
- Created `tests/test_embeddings.py` — 18 tests: upsert/remove/query/clear/persistence/project filter/n_results
- Fixed mypy issues with chromadb types (arg-type for metadatas, ClientAPI path)
- All 18 tests pass, ruff clean, mypy clean
- Updated spec_embeddings.md → READY

### E005 — 2026-04-07 23:53 — Step 4: index.py ReindexStats tracking
- Added `embedded`, `embedding_errors` counters and internal `_new_doc_ids`, `_stale_doc_ids`, `_removed_doc_ids` sets to ReindexStats
- Populated sets alongside existing counter increments in reindex() — 4 insertion points
- All 62 index tests pass, ruff clean, mypy clean. No existing behavior affected

### E006 — 2026-04-07 23:58 — Step 5: search.py — hybrid_search()
- Added hybrid_search() to search.py alongside existing search() (untouched)
- Constants: STEM_NORMALIZER=8.0, STEM_WEIGHT=0.55, EMBED_WEIGHT=0.45, EMBED_DISTANCE_THRESHOLD=1.4, CHUNK_ATTENUATION=0.2
- _aggregate_chunk_scores(): max + 0.2x attenuated extras, capped at 1.0
- Fallback: embedding_results=None returns raw stem scores (backward compat)
- Created tests/test_hybrid_search.py — 20 tests: fallback, both signals, embed-only, threshold, chunk aggregation, filters, scoring
- All 36 search tests pass (20 hybrid + 16 existing), ruff clean, mypy clean

### E007 — 2026-04-08 00:08 — Step 6: server.py — wire everything
- New globals: _embedding_backend, _private_embedding_backend
- _init_embeddings(): creates backends if config.embeddings and chromadb available, warning + fallback otherwise
- _sync_embeddings(): embeds new/stale docs after reindex, removes deleted, routes to shared/private backend
- _init(): calls _init_embeddings(), _sync_embeddings() on startup reindex
- search_docs(): queries both embedding backends, passes results to hybrid_search()
- get_cosmos(): reports embeddings_enabled and embedded_chunks
- reindex_tool(): reinitializes embedding backends, calls _sync_embeddings(), reports embedded/embedding_errors
- All 323 tests pass (64 server + rest), ruff clean, mypy clean

### E008 — 2026-04-08 00:08 — Step 7: web/state.py
- Added embedding_backend, private_embedding_backend to AppState
- search_cards() queries both backends, passes to hybrid_search()
- get_cosmos() reports embeddings_enabled, embedded_chunks
- do_reindex() calls _sync_embeddings() after save
- All 24 web tests pass, ruff clean, mypy clean

### E009 — 2026-04-08 00:12 — Step 8: pyproject.toml + config
- Added [embeddings] dep group (chromadb>=0.5) to pyproject.toml
- Added embeddings field + note to config.example.json
- Bumped version to 0.9.0
- pip install -e ".[embeddings,dev,web]" works
- All 323 tests pass

### E010 — 2026-04-08 00:20 — Step 9: Docs + final checks
- Updated ARCHITECTURE.md: added chunker, embeddings, embeddings_chroma modules, dependency graph, key decisions
- Full quality suite: ruff check + format + mypy + pytest — all clean, 323 tests pass
- All specs READY, PLAN.md all checked

### E011 — 2026-04-08 14:50 — Testing on real data + plan revision
- Tested hybrid search on 2112 docs / 44326 chunks
- Problems found:
  1. First-time enablement bug: all files "unchanged", nothing embedded → fixed with empty ChromaDB detection
  2. Search slow: every query pays ~1-2s for embedding query on 44k chunks
  3. Semantically imprecise: "ubuntu" doesn't find file containing "ubuntu" because embedding model maps it to different semantic space
  4. Short queries (agent's typical pattern) work worse than stemming
- Decision: split into separate `deep_search` tool — search_docs stays fast (pure stem), deep_search is on-demand semantic
- Cross-hints between tools: search_docs hints at deep_search when few results, deep_search hints back at search_docs
- New config field: `semantic_hint_threshold: int = 5`
- Updated PLAN.md with steps 10-14

### E012 — 2026-04-08 14:55 — Steps 10-14: Separate deep_search tool
- Step 10: Removed embedding query from search_docs(), restored pure stemming. Added hint to deep_search when results < semantic_hint_threshold
- Step 11: New MCP tool deep_search(query, project?, max_results?) — embedding-only, dedup by content_hash, error message when embeddings disabled, cross-hint to search_docs
- Step 12: AppConfig: added semantic_hint_threshold: int = 5. Updated config.example.json
- Step 13: web/state.py: restored search_cards() to pure stemming, added deep_search_cards() method, extracted _dedup_results() helper
- Step 14: Updated ChromaDB.md (changelog section: hybrid→separate tool, rationale), ARCHITECTURE.md (9 tools, updated description)
- All 323 tests pass, ruff clean, mypy clean
