"""Tests for hybrid search combining stem and embedding scores."""

from datetime import UTC, datetime

from astrolabe.embeddings import EmbeddingResult
from astrolabe.models import DocCard
from astrolabe.search import (
    CHUNK_ATTENUATION,
    EMBED_WEIGHT,
    STEM_NORMALIZER,
    STEM_WEIGHT,
    _aggregate_chunk_scores,
    hybrid_search,
)


def _card(
    project: str = "proj",
    filename: str = "doc.md",
    rel_path: str = "doc.md",
    *,
    type: str | None = None,
    summary: str | None = None,
    keywords: list[str] | None = None,
    headings: list[str] | None = None,
) -> DocCard:
    return DocCard(
        project=project,
        filename=filename,
        rel_path=rel_path,
        size=100,
        modified=datetime.now(UTC),
        content_hash="abc123",
        type=type,
        summary=summary,
        keywords=keywords,
        headings=headings,
        enriched_at=datetime.now(UTC) if summary else None,
        enriched_content_hash="abc123" if summary else None,
    )


class TestAggregateChunkScores:
    """Tests for _aggregate_chunk_scores."""

    def test_empty(self) -> None:
        assert _aggregate_chunk_scores([]) == 0.0

    def test_single_chunk(self) -> None:
        assert _aggregate_chunk_scores([0.8]) == 0.8

    def test_two_chunks(self) -> None:
        result = _aggregate_chunk_scores([0.8, 0.6])
        expected = 0.8 + 0.6 * CHUNK_ATTENUATION
        assert abs(result - expected) < 0.001

    def test_capped_at_one(self) -> None:
        result = _aggregate_chunk_scores([0.95, 0.9, 0.85, 0.8])
        assert result == 1.0

    def test_order_independent(self) -> None:
        result1 = _aggregate_chunk_scores([0.5, 0.8, 0.3])
        result2 = _aggregate_chunk_scores([0.3, 0.5, 0.8])
        assert abs(result1 - result2) < 0.001


class TestHybridSearchFallback:
    """Tests for hybrid_search when embedding_results=None (backward compat)."""

    def test_no_embeddings_returns_stem_scores(self) -> None:
        cards = [_card(keywords=["auth", "login"])]
        results = hybrid_search(cards, "auth", None)
        assert len(results) == 1
        # Raw stem score, not normalized
        assert results[0].relevance == 3.0  # keyword match * 3.0 weight

    def test_no_embeddings_empty_query(self) -> None:
        cards = [_card(keywords=["auth"])]
        results = hybrid_search(cards, "", None)
        assert results == []

    def test_no_embeddings_respects_project_filter(self) -> None:
        cards = [
            _card(project="a", rel_path="a.md", keywords=["auth"]),
            _card(project="b", rel_path="b.md", keywords=["auth"]),
        ]
        results = hybrid_search(cards, "auth", None, project="a")
        assert len(results) == 1
        assert results[0].project == "a"

    def test_no_embeddings_respects_type_filter(self) -> None:
        cards = [
            _card(rel_path="ref.md", type="reference", keywords=["auth"]),
            _card(rel_path="task.md", type="task", keywords=["auth"]),
        ]
        results = hybrid_search(cards, "auth", None, type="reference")
        assert len(results) == 1
        assert results[0].type == "reference"

    def test_no_embeddings_type_boosts(self) -> None:
        cards = [
            _card(rel_path="ref.md", type="reference", keywords=["auth"]),
            _card(rel_path="task.md", type="task", keywords=["auth"]),
        ]
        results = hybrid_search(cards, "auth", None, type_boosts={"reference": 2.0})
        assert results[0].type == "reference"
        assert results[0].relevance > results[1].relevance


class TestHybridSearchWithEmbeddings:
    """Tests for hybrid_search with embedding results."""

    def test_both_signals(self) -> None:
        cards = [_card(keywords=["auth", "login"], summary="Authentication guide")]
        embed_results = [
            EmbeddingResult(doc_id="proj::doc.md", score=0.75, chunk_text="auth content")
        ]
        results = hybrid_search(cards, "auth", embed_results)
        assert len(results) == 1
        # Should have combined score
        r = results[0]
        assert r.relevance > 0

    def test_embed_only_surfaces_unenriched(self) -> None:
        # Unenriched card (no keywords, summary, headings)
        cards = [_card(filename="auth_guide.md", rel_path="auth_guide.md")]
        embed_results = [
            EmbeddingResult(doc_id="proj::auth_guide.md", score=0.8, chunk_text="auth content")
        ]
        results = hybrid_search(cards, "login", embed_results)
        assert len(results) == 1
        # Score comes from embedding only (filename "auth_guide" won't match "login")
        assert results[0].relevance > 0

    def test_stem_only_no_embed_match(self) -> None:
        cards = [_card(keywords=["database"])]
        embed_results: list[EmbeddingResult] = []  # empty results
        results = hybrid_search(cards, "database", embed_results)
        assert len(results) == 1
        # Stem score normalized
        r = results[0]
        expected = min(3.0 / STEM_NORMALIZER, 1.0) * STEM_WEIGHT
        assert abs(r.relevance - round(expected, 4)) < 0.01

    def test_enriched_ranks_higher_than_unenriched(self) -> None:
        enriched = _card(
            rel_path="enriched.md",
            keywords=["authentication"],
            summary="Auth guide for API",
        )
        unenriched = _card(rel_path="unenriched.md", filename="unenriched.md")
        cards = [enriched, unenriched]
        embed_results = [
            EmbeddingResult(doc_id="proj::enriched.md", score=0.7, chunk_text="auth"),
            EmbeddingResult(doc_id="proj::unenriched.md", score=0.75, chunk_text="auth"),
        ]
        results = hybrid_search(cards, "authentication", embed_results)
        assert len(results) == 2
        # Enriched should rank first (stem + embed > embed only)
        assert results[0].doc_id == "proj::enriched.md"

    def test_embed_threshold_filters_noise(self) -> None:
        cards = [_card()]
        # Very low score (high distance > threshold)
        embed_results = [EmbeddingResult(doc_id="proj::doc.md", score=0.1, chunk_text="noise")]
        results = hybrid_search(cards, "something", embed_results)
        # Low score means high distance: (1 - 0.1) * 2 = 1.8 > 1.4 threshold
        assert len(results) == 0

    def test_multiple_chunks_aggregated(self) -> None:
        cards = [_card()]
        embed_results = [
            EmbeddingResult(doc_id="proj::doc.md", score=0.8, chunk_text="chunk 1"),
            EmbeddingResult(doc_id="proj::doc.md", score=0.6, chunk_text="chunk 2"),
        ]
        results = hybrid_search(cards, "query", embed_results)
        assert len(results) == 1
        # Aggregated: 0.8 + 0.6 * 0.2 = 0.92
        expected_embed = 0.8 + 0.6 * CHUNK_ATTENUATION
        expected_hybrid = round(0.0 * STEM_WEIGHT + expected_embed * EMBED_WEIGHT, 4)
        assert abs(results[0].relevance - expected_hybrid) < 0.01

    def test_project_filter_applied_to_embed_results(self) -> None:
        cards = [
            _card(project="a", rel_path="a.md"),
            _card(project="b", rel_path="b.md"),
        ]
        embed_results = [
            EmbeddingResult(doc_id="proj-a::a.md", score=0.8, chunk_text="content a"),
            EmbeddingResult(doc_id="proj-b::b.md", score=0.9, chunk_text="content b"),
        ]
        # Project filter on cards means embed results for filtered-out cards are also excluded
        results = hybrid_search(cards, "query", embed_results, project="a")
        assert all(r.project == "a" for r in results)

    def test_empty_embed_results_list(self) -> None:
        cards = [_card(keywords=["test"])]
        results = hybrid_search(cards, "test", [])
        assert len(results) == 1
        # Should be stem-only score, but normalized (not raw)
        expected = round(min(3.0 / STEM_NORMALIZER, 1.0) * STEM_WEIGHT, 4)
        assert abs(results[0].relevance - expected) < 0.01


class TestHybridSearchScoring:
    """Tests verifying specific scoring properties."""

    def test_stem_normalization(self) -> None:
        # A card matching keyword should normalize to < 1.0
        cards = [_card(keywords=["api"])]
        embed_results: list[EmbeddingResult] = []
        results = hybrid_search(cards, "api", embed_results)
        assert len(results) == 1
        # Raw stem = 3.0, normalized = 3.0/8.0 = 0.375, * 0.55 = 0.20625
        expected = round(min(3.0 / STEM_NORMALIZER, 1.0) * STEM_WEIGHT, 4)
        assert abs(results[0].relevance - expected) < 0.01

    def test_perfect_stem_clamped(self) -> None:
        # A card matching many fields should clamp at 1.0
        cards = [
            _card(
                filename="api_ref.md",
                keywords=["api"],
                headings=["API Reference"],
                summary="API reference documentation",
            )
        ]
        embed_results = [EmbeddingResult(doc_id="proj::doc.md", score=0.9, chunk_text="api ref")]
        results = hybrid_search(cards, "api", embed_results)
        assert len(results) == 1
        assert results[0].relevance <= 1.0
