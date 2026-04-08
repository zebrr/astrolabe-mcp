"""ChromaDB implementation of EmbeddingBackend."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrolabe.embeddings import EmbeddingResult

if TYPE_CHECKING:
    import chromadb

logger = logging.getLogger(__name__)


class ChromaEmbeddingBackend:
    """ChromaDB-based embedding backend with lazy initialization.

    Storage: .chromadb/ subdirectory inside index_dir.
    Model: ChromaDB's default embedding function (all-MiniLM-L6-v2 via onnxruntime).
    """

    def __init__(
        self,
        index_dir: Path,
        *,
        collection_name: str = "astrolabe",
    ) -> None:
        self._index_dir = index_dir
        self._collection_name = collection_name
        self._client: chromadb.api.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    def _ensure_initialized(self) -> chromadb.Collection:
        """Lazy init: create client and collection on first use."""
        if self._collection is not None:
            return self._collection

        import chromadb

        chroma_dir = self._index_dir / ".chromadb"
        chroma_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB initialized: %s (%d chunks)",
            chroma_dir,
            self._collection.count(),
        )
        return self._collection

    def upsert_document(self, doc_id: str, chunks: list[str], metadata: dict[str, str]) -> None:
        """Add or update embeddings for a document."""
        collection = self._ensure_initialized()

        # Remove existing chunks for this doc_id
        self._delete_by_doc_id(collection, doc_id)

        if not chunks:
            return

        # Insert new chunks
        ids = [f"{doc_id}::chunk_{i}" for i in range(len(chunks))]
        chunk_metadatas: list[Mapping[str, str | int | float | bool]] = [
            {**metadata, "chunk_index": i} for i in range(len(chunks))
        ]

        collection.add(
            ids=ids,
            documents=chunks,
            metadatas=chunk_metadatas,  # type: ignore[arg-type]
        )

    def remove_document(self, doc_id: str) -> None:
        """Remove all embeddings for a document."""
        collection = self._ensure_initialized()
        self._delete_by_doc_id(collection, doc_id)

    def query(
        self,
        text: str,
        *,
        n_results: int = 20,
        project: str | None = None,
    ) -> list[EmbeddingResult]:
        """Query for similar chunks."""
        collection = self._ensure_initialized()

        if collection.count() == 0:
            return []

        where: dict[str, Any] | None = None
        if project is not None:
            where = {"project": project}

        # Clamp n_results to collection size
        effective_n = min(n_results, collection.count())

        result = collection.query(
            query_texts=[text],
            n_results=effective_n,
            where=where,
            include=["distances", "metadatas", "documents"],
        )

        if not result["distances"] or not result["distances"][0]:
            return []

        distances = result["distances"][0]
        metadatas = result["metadatas"][0] if result["metadatas"] else []
        documents = result["documents"][0] if result["documents"] else []

        results: list[EmbeddingResult] = []
        for i, dist in enumerate(distances):
            meta = metadatas[i] if i < len(metadatas) else {}
            doc_text = documents[i] if i < len(documents) else ""
            # Convert cosine distance (0-2) to similarity (0-1)
            score = 1.0 - (dist / 2.0)
            results.append(
                EmbeddingResult(
                    doc_id=str(meta.get("doc_id", "")),
                    score=score,
                    chunk_text=doc_text or "",
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def clear(self) -> None:
        """Remove all embeddings."""
        if self._client is None:
            self._ensure_initialized()
        assert self._client is not None

        # Delete and recreate collection
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        """Number of embedded chunks."""
        collection = self._ensure_initialized()
        return int(collection.count())

    @staticmethod
    def _delete_by_doc_id(collection: chromadb.Collection, doc_id: str) -> None:
        """Delete all chunks matching a doc_id."""
        try:
            existing = collection.get(where={"doc_id": doc_id})
            if existing["ids"]:
                collection.delete(ids=existing["ids"])
        except Exception:
            # Collection may be empty or doc_id not found
            pass
