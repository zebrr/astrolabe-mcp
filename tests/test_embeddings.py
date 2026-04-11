"""Tests for embedding backend."""

from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb")

from astrolabe.embeddings import (  # noqa: E402
    EmbeddingBackend,
    EmbeddingResult,
    create_embedding_backend,
    is_embeddings_available,
)
from astrolabe.embeddings_chroma import ChromaEmbeddingBackend  # noqa: E402


class TestAvailability:
    """Tests for availability check."""

    def test_chromadb_available(self) -> None:
        assert is_embeddings_available() is True


class TestEmbeddingResult:
    """Tests for EmbeddingResult dataclass."""

    def test_creation(self) -> None:
        r = EmbeddingResult(doc_id="proj::doc.md", score=0.85, chunk_text="hello")
        assert r.doc_id == "proj::doc.md"
        assert r.score == 0.85
        assert r.chunk_text == "hello"


class TestFactory:
    """Tests for create_embedding_backend factory."""

    def test_creates_backend(self, tmp_path: Path) -> None:
        backend = create_embedding_backend(tmp_path)
        assert isinstance(backend, ChromaEmbeddingBackend)

    def test_protocol_compliance(self, tmp_path: Path) -> None:
        backend = create_embedding_backend(tmp_path)
        assert isinstance(backend, EmbeddingBackend)


class TestChromaEmbeddingBackend:
    """Tests for ChromaDB backend."""

    @pytest.fixture()
    def backend(self, tmp_path: Path) -> ChromaEmbeddingBackend:
        return ChromaEmbeddingBackend(tmp_path, collection_name="test")

    def test_empty_count(self, backend: ChromaEmbeddingBackend) -> None:
        assert backend.count == 0

    def test_upsert_and_count(self, backend: ChromaEmbeddingBackend) -> None:
        backend.upsert_document(
            "proj::doc.md",
            ["chunk one content", "chunk two content"],
            {"doc_id": "proj::doc.md", "project": "proj", "content_hash": "abc"},
        )
        assert backend.count == 2

    def test_upsert_replaces(self, backend: ChromaEmbeddingBackend) -> None:
        meta = {"doc_id": "proj::doc.md", "project": "proj", "content_hash": "abc"}
        backend.upsert_document("proj::doc.md", ["chunk one", "chunk two"], meta)
        assert backend.count == 2

        # Upsert with different chunks replaces
        backend.upsert_document("proj::doc.md", ["new single chunk"], meta)
        assert backend.count == 1

    def test_upsert_empty_chunks(self, backend: ChromaEmbeddingBackend) -> None:
        meta = {"doc_id": "proj::doc.md", "project": "proj", "content_hash": "abc"}
        backend.upsert_document("proj::doc.md", ["some content"], meta)
        assert backend.count == 1

        # Upsert with empty chunks removes all
        backend.upsert_document("proj::doc.md", [], meta)
        assert backend.count == 0

    def test_remove_document(self, backend: ChromaEmbeddingBackend) -> None:
        meta = {"doc_id": "proj::doc.md", "project": "proj", "content_hash": "abc"}
        backend.upsert_document("proj::doc.md", ["chunk one", "chunk two"], meta)
        assert backend.count == 2

        backend.remove_document("proj::doc.md")
        assert backend.count == 0

    def test_remove_nonexistent(self, backend: ChromaEmbeddingBackend) -> None:
        # Should not raise
        backend.remove_document("proj::missing.md")

    def test_query_returns_results(self, backend: ChromaEmbeddingBackend) -> None:
        backend.upsert_document(
            "proj::auth.md",
            ["Authentication with OAuth2 tokens and JWT verification"],
            {"doc_id": "proj::auth.md", "project": "proj", "content_hash": "a1"},
        )
        backend.upsert_document(
            "proj::readme.md",
            ["Project readme with installation instructions"],
            {"doc_id": "proj::readme.md", "project": "proj", "content_hash": "b2"},
        )

        results = backend.query("login authentication")
        assert len(results) >= 1
        assert all(isinstance(r, EmbeddingResult) for r in results)
        assert all(0.0 <= r.score <= 1.0 for r in results)
        # Auth doc should rank higher for auth query
        assert results[0].doc_id == "proj::auth.md"

    def test_query_empty_collection(self, backend: ChromaEmbeddingBackend) -> None:
        results = backend.query("anything")
        assert results == []

    def test_query_project_filter(self, backend: ChromaEmbeddingBackend) -> None:
        backend.upsert_document(
            "proj-a::doc.md",
            ["Authentication guide for project A"],
            {"doc_id": "proj-a::doc.md", "project": "proj-a", "content_hash": "a1"},
        )
        backend.upsert_document(
            "proj-b::doc.md",
            ["Authentication guide for project B"],
            {"doc_id": "proj-b::doc.md", "project": "proj-b", "content_hash": "b1"},
        )

        results = backend.query("authentication", project="proj-a")
        assert all(r.doc_id.startswith("proj-a") for r in results)

    def test_query_n_results(self, backend: ChromaEmbeddingBackend) -> None:
        for i in range(5):
            backend.upsert_document(
                f"proj::doc{i}.md",
                [f"Document number {i} about testing"],
                {"doc_id": f"proj::doc{i}.md", "project": "proj", "content_hash": f"h{i}"},
            )

        results = backend.query("testing", n_results=2)
        assert len(results) <= 2

    def test_clear(self, backend: ChromaEmbeddingBackend) -> None:
        meta = {"doc_id": "proj::doc.md", "project": "proj", "content_hash": "abc"}
        backend.upsert_document("proj::doc.md", ["some content"], meta)
        assert backend.count == 1

        backend.clear()
        assert backend.count == 0

    def test_creates_embeddings_dir(self, tmp_path: Path) -> None:
        embed_dir = tmp_path / "embeddings"
        backend = ChromaEmbeddingBackend(embed_dir, collection_name="test_dir")
        backend.upsert_document(
            "proj::doc.md",
            ["content"],
            {"doc_id": "proj::doc.md", "project": "proj", "content_hash": "abc"},
        )
        assert embed_dir.exists()

    def test_persistence(self, tmp_path: Path) -> None:
        embed_dir = tmp_path / "persist"
        # Write data
        backend1 = ChromaEmbeddingBackend(embed_dir, collection_name="persist_test")
        backend1.upsert_document(
            "proj::doc.md",
            ["persistent content"],
            {"doc_id": "proj::doc.md", "project": "proj", "content_hash": "abc"},
        )
        assert backend1.count == 1

        # Create new backend pointing to same dir
        backend2 = ChromaEmbeddingBackend(embed_dir, collection_name="persist_test")
        assert backend2.count == 1

    def test_multiple_documents(self, backend: ChromaEmbeddingBackend) -> None:
        for i in range(10):
            backend.upsert_document(
                f"proj::doc{i}.md",
                [f"Content for document {i} about topic {i}"],
                {"doc_id": f"proj::doc{i}.md", "project": "proj", "content_hash": f"h{i}"},
            )
        assert backend.count == 10

        # Remove one
        backend.remove_document("proj::doc5.md")
        assert backend.count == 9


class TestManifest:
    """Tests for embedding manifest (tracks what's been embedded)."""

    @pytest.fixture()
    def backend(self, tmp_path: Path) -> ChromaEmbeddingBackend:
        return ChromaEmbeddingBackend(tmp_path / "embeddings", collection_name="test")

    def test_empty_manifest(self, backend: ChromaEmbeddingBackend) -> None:
        assert backend.load_manifest() == {}

    def test_save_and_load(self, backend: ChromaEmbeddingBackend) -> None:
        manifest = {"proj::a.md": "hash1", "proj::b.md": "hash2"}
        backend.save_manifest(manifest)
        loaded = backend.load_manifest()
        assert loaded == manifest

    def test_clear_removes_manifest(self, backend: ChromaEmbeddingBackend) -> None:
        backend.save_manifest({"proj::a.md": "hash1"})
        backend.clear()
        assert backend.load_manifest() == {}

    def test_corrupt_manifest_returns_empty(self, tmp_path: Path) -> None:
        embed_dir = tmp_path / "embeddings"
        embed_dir.mkdir(parents=True)
        (embed_dir / "manifest.json").write_text("not json{{{", encoding="utf-8")
        backend = ChromaEmbeddingBackend(embed_dir, collection_name="test")
        assert backend.load_manifest() == {}

    def test_manifest_persists_across_instances(self, tmp_path: Path) -> None:
        embed_dir = tmp_path / "embeddings"
        b1 = ChromaEmbeddingBackend(embed_dir, collection_name="test")
        b1.save_manifest({"proj::doc.md": "abc123"})

        b2 = ChromaEmbeddingBackend(embed_dir, collection_name="test")
        assert b2.load_manifest() == {"proj::doc.md": "abc123"}
