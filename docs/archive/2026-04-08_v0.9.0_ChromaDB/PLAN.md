# PLAN — Astrolabe ChromaDB Semantic Search v0.9.0

Feature description: `docs/ChromaDB.md`

- [x] **Step 0**: Project setup — `docs/ChromaDB.md` (architecture), specs DRAFT (`spec_chunker.md`, `spec_embeddings.md`), `PLAN.md` + `PROGRESS.md`
- [x] **Step 1**: `chunker.py` — paragraph-aware file chunking + `tests/test_chunker.py`
- [x] **Step 2**: `models.py` — AppConfig: `embeddings: bool = False`, CosmosResponse: `embeddings_enabled`, `embedded_chunks`
- [x] **Step 3**: `embeddings.py` + `embeddings_chroma.py` — EmbeddingBackend Protocol, ChromaDB implementation, factory + `tests/test_embeddings.py`
- [x] **Step 4**: `index.py` — ReindexStats: `embedded`, `embedding_errors`, internal `_new_doc_ids`/`_stale_doc_ids`/`_removed_doc_ids` sets
- [x] **Step 5**: `search.py` — `hybrid_search()` function + `tests/test_hybrid_search.py`
- [x] **Step 6**: `server.py` — wire embeddings into `_init()`, `search_docs()`, `reindex_tool()`, `get_cosmos()`
- [x] **Step 7**: `web/state.py` — mirror server.py embedding integration for web UI
- [x] **Step 8**: `pyproject.toml` + `config.example.json` — `[embeddings]` dep group, `embeddings` field, version bump 0.9.0
- [x] **Step 9**: Docs + final checks — ARCHITECTURE.md, spec statuses, full quality suite

Updated: 2026-04-08 — after testing hybrid search proved too slow and semantically imprecise for short queries. Splitting into separate deep_search tool instead of embedding into search_docs.

- [x] **Step 10**: `server.py` — remove embedding query from `search_docs`, restore pure stemming. Add hint to `deep_search` when results < `semantic_hint_threshold`
- [x] **Step 11**: New MCP tool `deep_search(query, project?)` — embedding-only search, dedup by content_hash, hint back to `search_docs`
- [x] **Step 12**: `models.py` — AppConfig: add `semantic_hint_threshold: int = 5`. Update `config.example.json`
- [x] **Step 13**: `web/state.py` + `routes_api.py` — mirror deep_search for web UI
- [x] **Step 14**: Docs — update ChromaDB.md (changelog: hybrid→separate tool), ARCHITECTURE.md (new tool), tests, quality suite
