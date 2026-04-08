# ChromaDB Semantic Search — Architecture

> Astrolabe v0.9.0: optional embedding-based search over file content.

## Problem

Current search works only over enriched metadata (keywords, summary, headings, filename) via bilingual stemming. This means:
- Unenriched cards are invisible to search (except filename matches)
- Synonyms and related concepts are not found ("login" doesn't find "authentication")
- Cross-language semantic matching doesn't work
- Agent must enrich every card before search is useful

## Solution

ChromaDB with built-in embeddings (all-MiniLM-L6-v2, ~80MB model, runs locally, no API keys). Files are chunked and embedded at index time. Search queries both the stem index and vector store, merging results with weighted scoring.

### Principles

1. **Optional** — disabled by default, enabled via `"embeddings": true` in config.json
2. **Zero API cost** — ChromaDB's built-in model, no external services
3. **Backward compatible** — without embeddings, identical to v0.8.x
4. **Automatic** — embeddings update on reindex, no manual step
5. **Lazy** — model loaded on first use, not at startup
6. **Dual storage** — shared ChromaDB next to shared index, private next to private index

## Config

```json
{
  "embeddings": true
}
```

Single boolean field in config.json. All other parameters (chunk size, weights, model) are internal constants — not exposed to users in v0.9.0.

Requires: `pip install astrolabe-mcp[embeddings]`

If `embeddings: true` but chromadb not installed — warning logged, stem-only fallback.

## Storage Layout

```
index_dir/                      # e.g. runtime/ or cloud folder
├── .doc-index.json             # existing index
├── .doc-index.db               # existing SQLite index
├── doc_types.yaml              # existing
└── .chromadb/                  # NEW: ChromaDB persistent data
    └── (chroma internal files)

private_index_dir/              # e.g. ~/.astrolabe/private/
├── .doc-index.json
└── .chromadb/                  # NEW: separate ChromaDB for private
    └── (chroma internal files)
```

ChromaDB data co-located with its corresponding index, respecting shared/private boundary.

## Chunking Strategy

File → chunks of ~800 characters with ~100 character overlap.

1. Read file as UTF-8 (skip binary files)
2. Skip files larger than max_file_size_kb
3. Split by paragraphs (double newline), then reassemble into chunks
4. If paragraph exceeds chunk size — split by sentences, then hard-split
5. Minimum chunk: 20 characters (filter noise)
6. Each chunk stored in ChromaDB with metadata: `doc_id`, `project`, `chunk_index`, `content_hash`

### Constants

```python
CHUNK_SIZE = 800          # characters per chunk
CHUNK_OVERLAP = 100       # overlap between chunks
MIN_CHUNK_SIZE = 20       # skip tiny chunks
MAX_EMBED_FILE_KB = 500   # skip huge files
```

## Hybrid Search Algorithm

### Scoring

Two independent scoring paths, merged with weights:

```
stem_score   = existing _score_card() logic (field weights: keywords 3.0, headings 2.0, summary 1.5, filename 0.8)
embed_score  = ChromaDB similarity (cosine), aggregated per document from chunk results

stem_norm    = min(stem_score / STEM_NORMALIZER, 1.0)    # normalize to [0, 1]
final        = stem_norm * STEM_WEIGHT + embed_score * EMBED_WEIGHT
```

### Constants

```python
STEM_NORMALIZER = 8.0         # a "very good" stem match ≈ 1.0
STEM_WEIGHT = 0.55            # slight preference for exact matches
EMBED_WEIGHT = 0.45           # semantic matches complement
EMBED_DISTANCE_THRESHOLD = 1.4  # cosine distance > 1.4 = noise
CHUNK_ATTENUATION = 0.2       # contribution of non-best chunks
```

### Chunk-to-Document Aggregation

A document may have multiple matching chunks. Aggregation:

```python
sorted_sims = sorted(chunk_similarities, reverse=True)
embed_score = min(sorted_sims[0] + sum(s * 0.2 for s in sorted_sims[1:]), 1.0)
```

Best chunk dominates; additional chunks contribute 20% each. Prevents long documents from outranking short focused documents.

### Fallback Behavior

- **No embedding results** (disabled or unavailable) → pure stem search, raw scores (backward compat)
- **No stem matches** (unenriched card) → pure embedding score × EMBED_WEIGHT
- **Both signals** → weighted combination (best quality)

### Score Examples

| Scenario | Stem Raw | Stem Norm | Embed | Hybrid |
|---|---|---|---|---|
| Enriched, keyword + embed match | 6.5 | 0.81 | 0.75 | **0.78** |
| Enriched, keyword only | 3.0 | 0.375 | 0.0 | **0.21** |
| Unenriched, embed only | 0.0 | 0.0 | 0.65 | **0.29** |
| Unenriched, filename + embed | 0.8 | 0.1 | 0.70 | **0.37** |
| Enriched, strong all-field | 8.0 | 1.0 | 0.85 | **0.93** |

Enriched cards naturally rank higher (both signals contribute).

## Reindex + Embedding Flow

```
reindex() → (new_index, stats)
    ↓
_save_index()                   # existing: persist to JSON/SQLite
    ↓
_sync_embeddings()              # NEW: update ChromaDB
  - rebuild mode → clear() all embeddings first
  - For each NEW doc_id (stats._new_doc_ids):
      read file → chunk_file() → backend.upsert_document()
  - For each STALE doc_id (stats._stale_doc_ids):
      read file → chunk_file() → backend.upsert_document()
  - For each REMOVED doc_id (stats._removed_doc_ids):
      backend.remove_document()
  - Route to shared/private backend by config.is_private()
```

**Key**: embeddings update automatically on reindex. Card enrichment (update_index_tool) does NOT re-embed — file content hasn't changed, only metadata did.

## Module Architecture

```
models.py    ← config.py ← index.py    ← server.py
models.py    ← reader.py ←─────────────┘
models.py    ← search.py ←─────────────┘
chunker.py   ← embeddings.py ←─────────┘
               embeddings_chroma.py ←───┘
```

### New Modules

| Module | Depends on | Purpose |
|--------|-----------|---------|
| `chunker.py` | (none) | File → text chunks |
| `embeddings.py` | chunker, models | EmbeddingBackend Protocol, EmbeddingResult, factory |
| `embeddings_chroma.py` | embeddings | ChromaDB implementation |

### EmbeddingBackend Protocol

```python
class EmbeddingBackend(Protocol):
    def upsert_document(self, doc_id: str, chunks: list[str], metadata: dict[str, str]) -> None: ...
    def remove_document(self, doc_id: str) -> None: ...
    def query(self, text: str, *, n_results: int = 20, project: str | None = None) -> list[EmbeddingResult]: ...
    def clear(self) -> None: ...
    @property
    def count(self) -> int: ...
```

Mirrors `StorageBackend` pattern: Protocol + factory + concrete implementation.

## Performance

| Metric | 1,500 cards | 15,000 cards |
|--------|------------|--------------|
| Chunks | ~4,500 | ~45,000 |
| First index | ~1-2 min | ~10-15 min |
| Disk (ChromaDB) | ~50-100 MB | ~500 MB - 1 GB |
| RAM (model) | ~200 MB | ~200 MB |
| Search query | <50 ms | <100 ms |
| Incremental reindex | seconds | seconds |
| Server startup (lazy) | +0 ms | +0 ms |
| First search (cold) | +2-3 sec | +2-3 sec |

Model loads once on first use, stays in RAM for session duration.

## Limitations

- ChromaDB's `.chromadb/` directory may not sync reliably via cloud drives (multiple files, WAL mode). Shared teams should treat embeddings as local-only and re-embed on each machine
- Binary files (PDF, Office, images) are not embedded — no content extraction
- Embedding model is fixed (all-MiniLM-L6-v2) — no model choice in v0.9.0
- No incremental chunk updates — entire document re-chunked on change

## Changelog

### v0.9.0-rc2: Hybrid → Separate Tool

**Problem**: Initial implementation embedded ChromaDB query into `search_docs()` (hybrid scoring). Testing on real data (2112 docs, 44k chunks) revealed:
1. **Slow**: every search paid ~1-2s for embedding query, vs instant stemming
2. **Imprecise for short queries**: "ubuntu" didn't find a file containing "ubuntu" — embedding model maps it to a different semantic space
3. **Short queries dominate**: agents search with "auth api", not paragraphs — stemming wins here

**Solution**: Split into separate `deep_search` tool.
- `search_docs` — pure stemming, fast, exact keyword matching (restored to pre-embedding behavior)
- `deep_search` — on-demand semantic search, only when explicitly called
- Cross-hints: `search_docs` suggests `deep_search` when results < `semantic_hint_threshold` (5). `deep_search` always hints back to `search_docs`
- `hybrid_search()` function retained in search.py — used by `deep_search` to combine stem + embedding scores

**Key insight**: semantic search is a **complement** to keyword search, not a replacement. Best used when the user doesn't know the exact term or when keyword search finds nothing.
