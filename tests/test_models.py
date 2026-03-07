"""Tests for astrolabe.models."""

from datetime import UTC, datetime
from pathlib import Path

from astrolabe import __version__
from astrolabe.models import (
    AppConfig,
    CosmosResponse,
    DocCard,
    IndexData,
    ProjectSummary,
    SearchResult,
    TypeSummary,
)


class TestAppConfig:
    def test_basic_creation(self) -> None:
        config = AppConfig(
            projects={"neyra": Path("/projects/neyra")},
            index_path=Path(".doc-index.json"),
            index_extensions=[".md"],
            ignore_dirs=[".git"],
            ignore_files=["*.pyc"],
            max_file_size_kb=100,
        )
        assert config.projects["neyra"] == Path("/projects/neyra")
        assert config.max_file_size_kb == 100

    def test_multiple_projects(self) -> None:
        config = AppConfig(
            projects={
                "a": Path("/a"),
                "b": Path("/b"),
                "c": Path("/c"),
            },
            index_path=Path(".doc-index.json"),
            index_extensions=[".md", ".yaml"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=50,
        )
        assert len(config.projects) == 3
        assert len(config.index_extensions) == 2


class TestDocCard:
    def _make_card(self, **kwargs: object) -> DocCard:
        defaults: dict[str, object] = {
            "project": "neyra",
            "filename": "README.md",
            "rel_path": "README.md",
            "size": 1200,
            "modified": datetime(2026, 3, 6, tzinfo=UTC),
            "content_hash": "abc123",
        }
        defaults.update(kwargs)
        return DocCard(**defaults)  # type: ignore[arg-type]

    def test_doc_id(self) -> None:
        card = self._make_card()
        assert card.doc_id == "neyra::README.md"

    def test_doc_id_nested_path(self) -> None:
        card = self._make_card(rel_path="docs/references/Ref.md")
        assert card.doc_id == "neyra::docs/references/Ref.md"

    def test_is_empty_when_not_enriched(self) -> None:
        card = self._make_card()
        assert card.is_empty is True
        assert card.is_stale is False

    def test_is_stale_when_modified_after_enrichment(self) -> None:
        card = self._make_card(
            modified=datetime(2026, 3, 6, 12, 0, tzinfo=UTC),
            enriched_at=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
        )
        assert card.is_stale is True
        assert card.is_empty is False

    def test_not_stale_when_enriched_after_modification(self) -> None:
        card = self._make_card(
            modified=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
            enriched_at=datetime(2026, 3, 6, 12, 0, tzinfo=UTC),
        )
        assert card.is_stale is False
        assert card.is_empty is False

    def test_enrichment_fields_default_none(self) -> None:
        card = self._make_card()
        assert card.type is None
        assert card.headings is None
        assert card.summary is None
        assert card.keywords is None
        assert card.enriched_at is None

    def test_enrichment_fields_set(self) -> None:
        card = self._make_card(
            type="reference",
            summary="A reference doc",
            keywords=["api", "mcp"],
            headings=["Setup", "Usage"],
            enriched_at=datetime(2026, 3, 6, tzinfo=UTC),
        )
        assert card.type == "reference"
        assert card.keywords == ["api", "mcp"]
        assert card.headings == ["Setup", "Usage"]

    def test_serialization_roundtrip(self) -> None:
        card = self._make_card(
            type="spec",
            summary="Test spec",
            keywords=["test"],
            enriched_at=datetime(2026, 3, 6, tzinfo=UTC),
        )
        data = card.model_dump()
        restored = DocCard.model_validate(data)
        assert restored.doc_id == card.doc_id
        assert restored.type == "spec"


class TestIndexData:
    def test_empty_index(self) -> None:
        index = IndexData(indexed_at=datetime(2026, 3, 6, tzinfo=UTC))
        assert index.version == __version__
        assert len(index.documents) == 0

    def test_index_with_documents(self) -> None:
        card = DocCard(
            project="neyra",
            filename="README.md",
            rel_path="README.md",
            size=100,
            modified=datetime(2026, 3, 6, tzinfo=UTC),
            content_hash="abc",
        )
        index = IndexData(
            indexed_at=datetime(2026, 3, 6, tzinfo=UTC),
            documents={card.doc_id: card},
        )
        assert len(index.documents) == 1
        assert "neyra::README.md" in index.documents

    def test_serialization_roundtrip(self) -> None:
        card = DocCard(
            project="k2",
            filename="arch.md",
            rel_path="docs/arch.md",
            size=500,
            modified=datetime(2026, 3, 6, tzinfo=UTC),
            content_hash="def456",
        )
        index = IndexData(
            indexed_at=datetime(2026, 3, 6, tzinfo=UTC),
            documents={card.doc_id: card},
        )
        data = index.model_dump(mode="json")
        restored = IndexData.model_validate(data)
        assert restored.version == __version__
        assert "k2::docs/arch.md" in restored.documents


class TestCosmosResponse:
    def test_creation(self) -> None:
        resp = CosmosResponse(
            server_version="0.2.2",
            indexed_at=datetime(2026, 3, 6, tzinfo=UTC),
            total_documents=48,
            enriched_documents=35,
            stale_documents=4,
            empty_documents=9,
            projects=[
                ProjectSummary(
                    id="neyra",
                    doc_count=24,
                    enriched_count=20,
                    last_indexed=datetime(2026, 3, 6, tzinfo=UTC),
                ),
            ],
            document_types=[
                TypeSummary(type="reference", description="Reference material", count=8),
            ],
        )
        assert resp.total_documents == 48
        assert len(resp.projects) == 1
        assert resp.projects[0].id == "neyra"
        assert len(resp.document_types) == 1


class TestSearchResult:
    def test_creation(self) -> None:
        result = SearchResult(
            doc_id="neyra::docs/ref.md",
            project="neyra",
            type="reference",
            filename="ref.md",
            summary="A reference",
            keywords=["api"],
            relevance=0.95,
        )
        assert result.relevance == 0.95
        assert result.doc_id == "neyra::docs/ref.md"

    def test_with_none_fields(self) -> None:
        result = SearchResult(
            doc_id="k2::README.md",
            project="k2",
            type=None,
            filename="README.md",
            summary=None,
            keywords=None,
            relevance=0.5,
        )
        assert result.type is None
        assert result.summary is None
