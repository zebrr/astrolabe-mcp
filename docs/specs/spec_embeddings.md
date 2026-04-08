# Spec: embeddings.py + embeddings_chroma.py

**Status**: READY

## Purpose

Embedding backend abstraction and ChromaDB implementation. Mirrors `storage.py` / `storage_json.py` / `storage_sqlite.py` pattern: Protocol + factory + concrete implementation.

## embeddings.py — Protocol and Factory

### EmbeddingResult

```python
@dataclass
class EmbeddingResult:
    doc_id: str
    score: float       # 0.0 to 1.0, higher = more similar
    chunk_text: str    # the matching chunk content
```

### EmbeddingBackend Protocol

```python
@runtime_checkable
class EmbeddingBackend(Protocol):
    def upsert_document(self, doc_id: str, chunks: list[str], metadata: dict[str, str]) -> None: ...
    def remove_document(self, doc_id: str) -> None: ...
    def query(self, text: str, *, n_results: int = 20, project: str | None = None) -> list[EmbeddingResult]: ...
    def clear(self) -> None: ...
    @property
    def count(self) -> int: ...
```

**Methods:**
- `upsert_document(doc_id, chunks, metadata)` — delete existing chunks for doc_id, insert new ones. Metadata: `{"doc_id": ..., "project": ..., "content_hash": ...}`
- `remove_document(doc_id)` — delete all chunks for doc_id
- `query(text, n_results, project)` — semantic search. Returns EmbeddingResult list sorted by score descending. Optional project filter pushed to ChromaDB `where` clause
- `clear()` — remove all embeddings (used in rebuild mode)
- `count` — total number of embedded chunks

### Factory Functions

```python
def is_embeddings_available() -> bool:
    """Check if chromadb is importable."""

def create_embedding_backend(index_dir: Path, *, collection_name: str = "astrolabe") -> EmbeddingBackend:
    """Create ChromaDB backend. Raises ImportError if chromadb not installed."""
```

## embeddings_chroma.py — ChromaDB Implementation

### ChromaEmbeddingBackend

```python
class ChromaEmbeddingBackend:
    def __init__(self, index_dir: Path, *, collection_name: str = "astrolabe") -> None: ...
```

**Storage:** `.chromadb/` subdirectory inside `index_dir`.

**Lazy initialization:** ChromaDB PersistentClient created on first method call (`_ensure_initialized()`). Model loads at that point (~2-3 sec cold start).

**Collection config:** cosine distance space (`hnsw:space: cosine`).

**Chunk ID scheme:** `{doc_id}::chunk_{i}` where `i` is 0-based chunk index.

**Metadata per chunk:**
```python
{
    "doc_id": "project::rel_path",
    "project": "my-project",
    "content_hash": "abc123",
    "chunk_index": 0,
}
```

**Query flow:**
1. ChromaDB returns distances (cosine, 0-2 range)
2. Convert to similarity: `score = 1.0 - (distance / 2.0)`
3. Return EmbeddingResult per chunk, sorted by score descending

**Upsert flow:**
1. Delete all existing chunks with matching doc_id (via `where={"doc_id": doc_id}`)
2. Insert new chunks with IDs `{doc_id}::chunk_{0..N}`

## Integration Points

- **server.py**: globals `_embedding_backend`, `_private_embedding_backend`
- **search_docs()**: query backends → pass results to `hybrid_search()`
- **reindex_tool()**: `_sync_embeddings()` after `_save_index()`
- **get_cosmos()**: report `embeddings_enabled`, `embedded_chunks`
