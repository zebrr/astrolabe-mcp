"""Bilingual morphological search over enriched DocCards with field weights."""

from collections.abc import Iterable

import snowballstemmer  # type: ignore[import-untyped]

from astrolabe.models import DocCard, SearchResult

_stemmer_en = snowballstemmer.stemmer("english")
_stemmer_ru = snowballstemmer.stemmer("russian")

FIELD_WEIGHTS: dict[str, float] = {
    "keywords": 3.0,
    "headings": 2.0,
    "summary": 1.5,
    "filename": 0.8,
}


def _stems(word: str) -> frozenset[str]:
    """Return EN + RU stems for a word."""
    w = word.lower()
    return frozenset(
        [
            _stemmer_en.stemWord(w),
            _stemmer_ru.stemWord(w),
        ]
    )


def _score_token_in_field(token: str, field_value: str) -> float:
    """Score a single token against a field value using stem matching."""
    token_stems = _stems(token)
    words = field_value.lower().split()
    for word in words:
        if token_stems & _stems(word):
            return 1.0
    return 0.0


def _score_card(card: DocCard, tokens: list[str]) -> float:
    """Compute relevance score for a card against query tokens."""
    score = 0.0

    for token in tokens:
        # filename — split on _, -, . then score word by word
        filename_as_text = card.filename.replace("_", " ").replace("-", " ").replace(".", " ")
        s = _score_token_in_field(token, filename_as_text)
        score += s * FIELD_WEIGHTS["filename"]

        # Enrichment fields
        if card.keywords:
            for kw in card.keywords:
                s = _score_token_in_field(token, kw)
                score += s * FIELD_WEIGHTS["keywords"]

        if card.headings:
            for heading in card.headings:
                s = _score_token_in_field(token, heading)
                score += s * FIELD_WEIGHTS["headings"]

        if card.summary:
            s = _score_token_in_field(token, card.summary)
            score += s * FIELD_WEIGHTS["summary"]

    return score


def search(
    cards: Iterable[DocCard],
    query: str,
    *,
    project: str | None = None,
    type: str | None = None,
    type_boosts: dict[str, float] | None = None,
) -> list[SearchResult]:
    """Search enriched cards by query with bilingual stem matching.

    Args:
        cards: Iterable of DocCards to search.
        query: Search query string.
        project: Optional project filter.
        type: Optional document type filter.
        type_boosts: Optional dict of type_name → multiplier from doc_types.yaml.
            Types not in the dict default to 1.0.

    Returns:
        List of SearchResult sorted by relevance descending.
    """
    tokens = query.lower().split()
    if not tokens:
        return []

    results: list[SearchResult] = []

    for card in cards:
        # Apply filters
        if project is not None and card.project != project:
            continue
        if type is not None and card.type != type:
            continue

        score = _score_card(card, tokens)
        if score > 0:
            # Apply type-based boost
            if type_boosts and card.type:
                score *= type_boosts.get(card.type, 1.0)
            results.append(
                SearchResult(
                    doc_id=card.doc_id,
                    project=card.project,
                    type=card.type,
                    filename=card.filename,
                    summary=card.summary,
                    keywords=card.keywords,
                    relevance=round(score, 2),
                )
            )

    results.sort(key=lambda r: r.relevance, reverse=True)
    return results
