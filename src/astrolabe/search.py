"""Text search over enriched DocCards with field weights."""

from collections.abc import Iterable

from astrolabe.models import DocCard, SearchResult

FIELD_WEIGHTS: dict[str, float] = {
    "keywords": 3.0,
    "filename": 2.5,
    "headings": 2.0,
    "summary": 1.0,
}

EXACT_BONUS = 1.5


def _score_token_in_field(token: str, field_value: str) -> float:
    """Score a single token against a field value (case-insensitive)."""
    lower_field = field_value.lower()
    if token not in lower_field:
        return 0.0
    # Exact word match bonus
    words = lower_field.split()
    if token in words:
        return EXACT_BONUS
    return 1.0


def _score_card(card: DocCard, tokens: list[str]) -> float:
    """Compute relevance score for a card against query tokens."""
    score = 0.0

    for token in tokens:
        # filename — always available
        s = _score_token_in_field(token, card.filename)
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
) -> list[SearchResult]:
    """Search enriched cards by query with field weights.

    Args:
        cards: Iterable of DocCards to search.
        query: Search query string.
        project: Optional project filter.
        type: Optional document type filter.

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
