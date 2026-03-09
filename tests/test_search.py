"""Tests for astrolabe.search."""

from datetime import UTC, datetime

from astrolabe.models import DocCard
from astrolabe.search import search


def _card(
    project: str = "proj",
    filename: str = "doc.md",
    rel_path: str = "doc.md",
    *,
    type: str | None = None,
    summary: str | None = None,
    keywords: list[str] | None = None,
    headings: list[str] | None = None,
    enriched: bool = False,
) -> DocCard:
    return DocCard(
        project=project,
        filename=filename,
        rel_path=rel_path,
        size=100,
        modified=datetime(2026, 3, 6, tzinfo=UTC),
        content_hash="abc",
        type=type,
        summary=summary,
        keywords=keywords,
        headings=headings,
        enriched_at=datetime(2026, 3, 6, tzinfo=UTC) if enriched else None,
    )


class TestSearch:
    def test_matches_keyword(self) -> None:
        cards = [_card(keywords=["telegram", "bot"], enriched=True)]
        results = search(cards, "telegram")
        assert len(results) == 1
        assert results[0].relevance > 0

    def test_matches_filename(self) -> None:
        cards = [_card(filename="telegram-ref.md")]
        results = search(cards, "telegram")
        assert len(results) == 1

    def test_matches_summary(self) -> None:
        cards = [_card(summary="Guide to Telegram API usage", enriched=True)]
        results = search(cards, "telegram")
        assert len(results) == 1

    def test_matches_headings(self) -> None:
        cards = [_card(headings=["Setup", "Telegram Configuration"], enriched=True)]
        results = search(cards, "telegram")
        assert len(results) == 1

    def test_no_match(self) -> None:
        cards = [_card(keywords=["python"], enriched=True)]
        results = search(cards, "telegram")
        assert len(results) == 0

    def test_keywords_weighted_higher(self) -> None:
        card_kw = _card(
            filename="a.md",
            rel_path="a.md",
            keywords=["telegram"],
            enriched=True,
        )
        card_summary = _card(
            filename="b.md",
            rel_path="b.md",
            summary="telegram guide",
            enriched=True,
        )
        results = search([card_kw, card_summary], "telegram")
        assert len(results) == 2
        # keyword match should score higher
        assert results[0].doc_id == card_kw.doc_id

    def test_filter_by_project(self) -> None:
        cards = [
            _card(project="a", keywords=["test"], enriched=True),
            _card(project="b", filename="b.md", rel_path="b.md", keywords=["test"], enriched=True),
        ]
        results = search(cards, "test", project="a")
        assert len(results) == 1
        assert results[0].project == "a"

    def test_filter_by_type(self) -> None:
        cards = [
            _card(type="reference", keywords=["api"], enriched=True),
            _card(
                filename="task.md",
                rel_path="task.md",
                type="task",
                keywords=["api"],
                enriched=True,
            ),
        ]
        results = search(cards, "api", type="reference")
        assert len(results) == 1
        assert results[0].type == "reference"

    def test_empty_query(self) -> None:
        cards = [_card(keywords=["test"], enriched=True)]
        results = search(cards, "")
        assert len(results) == 0

    def test_multi_token_query(self) -> None:
        cards = [_card(keywords=["telegram", "bot"], summary="Telegram bot API", enriched=True)]
        results = search(cards, "telegram bot")
        assert len(results) == 1
        assert results[0].relevance > 0

    def test_case_insensitive(self) -> None:
        cards = [_card(keywords=["Telegram"], enriched=True)]
        results = search(cards, "TELEGRAM")
        assert len(results) == 1

    def test_sorted_by_relevance(self) -> None:
        cards = [
            _card(filename="low.md", rel_path="low.md", summary="some text", enriched=True),
            _card(
                filename="high.md",
                rel_path="high.md",
                keywords=["target", "exact"],
                summary="about target",
                headings=["Target Section"],
                enriched=True,
            ),
        ]
        results = search(cards, "target")
        assert results[0].doc_id == "proj::high.md"

    def test_ru_morphology(self) -> None:
        """Russian stemming: plural form matches singular keyword."""
        cards = [_card(keywords=["документ"], enriched=True)]
        results = search(cards, "документы")
        assert len(results) == 1

    def test_en_morphology(self) -> None:
        """English stemming: 'running' matches 'run'."""
        cards = [_card(summary="task is running in background", enriched=True)]
        results = search(cards, "run")
        assert len(results) == 1

    def test_filename_word_split(self) -> None:
        """Filename snake_case is split into words for matching."""
        cards = [_card(filename="spec_search.md")]
        results = search(cards, "search")
        assert len(results) == 1

    def test_summary_weighted_above_filename(self) -> None:
        """Summary (1.5) scores higher than filename (0.8) for same token."""
        card_fn = _card(filename="search.md", rel_path="search.md")
        card_sm = _card(
            filename="b.md",
            rel_path="b.md",
            summary="search engine documentation",
            enriched=True,
        )
        results = search([card_fn, card_sm], "search")
        assert results[0].doc_id == card_sm.doc_id
