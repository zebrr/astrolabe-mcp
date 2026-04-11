"""Embedding backend abstraction for semantic search."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Single result from an embedding query."""

    doc_id: str
    score: float  # 0.0 to 1.0, higher is more similar
    chunk_text: str


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Protocol for document embedding backends."""

    def upsert_document(self, doc_id: str, chunks: list[str], metadata: dict[str, str]) -> None:
        """Add or update embeddings for a document.

        Removes existing chunks for doc_id, then inserts new ones.

        Args:
            doc_id: Document identifier (project::rel_path).
            chunks: List of text chunks from the document.
            metadata: Shared metadata for all chunks (doc_id, project, content_hash).
        """
        ...

    def remove_document(self, doc_id: str) -> None:
        """Remove all embeddings for a document."""
        ...

    def query(
        self,
        text: str,
        *,
        n_results: int = 20,
        project: str | None = None,
    ) -> list[EmbeddingResult]:
        """Query for similar documents.

        Args:
            text: Query text.
            n_results: Maximum number of chunk results.
            project: Optional project filter.

        Returns:
            List of EmbeddingResult sorted by score descending.
        """
        ...

    def clear(self) -> None:
        """Remove all embeddings and manifest (used during rebuild)."""
        ...

    @property
    def count(self) -> int:
        """Number of embedded chunks."""
        ...

    def load_manifest(self) -> dict[str, str]:
        """Load embedding manifest: {doc_id: content_hash} for embedded docs."""
        ...

    def save_manifest(self, manifest: dict[str, str]) -> None:
        """Save embedding manifest to disk."""
        ...


def is_embeddings_available() -> bool:
    """Check if chromadb is importable."""
    try:
        import chromadb  # noqa: F401

        return True
    except ImportError:
        return False


def create_embedding_backend(
    embeddings_dir: Path,
    *,
    collection_name: str = "astrolabe",
) -> "EmbeddingBackend":
    """Create a ChromaDB embedding backend.

    Args:
        embeddings_dir: Directory for ChromaDB persistent storage (local, not cloud-synced).
        collection_name: ChromaDB collection name.

    Returns:
        ChromaEmbeddingBackend instance.

    Raises:
        ImportError: If chromadb is not installed.
    """
    from astrolabe.embeddings_chroma import ChromaEmbeddingBackend

    return ChromaEmbeddingBackend(embeddings_dir, collection_name=collection_name)
