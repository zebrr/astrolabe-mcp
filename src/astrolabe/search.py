"""Bilingual morphological search over enriched DocCards with field weights."""

from __future__ import annotations

from collections.abc import Iterable

import snowballstemmer  # type: ignore[import-untyped]

from astrolabe.embeddings import EmbeddingResult
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


# Hybrid search constants
STEM_NORMALIZER = 8.0
STEM_WEIGHT = 0.55
EMBED_WEIGHT = 0.45
EMBED_DISTANCE_THRESHOLD = 1.4
CHUNK_ATTENUATION = 0.2


def _aggregate_chunk_scores(similarities: list[float]) -> float:
    """Aggregate chunk similarities into a single document embedding score.

    Uses max chunk score + attenuated contribution from additional chunks.
    Rewards documents with multiple relevant sections without letting
    a document with many mediocre chunks outrank one with a single perfect chunk.
    """
    if not similarities:
        return 0.0
    sorted_sims = sorted(similarities, reverse=True)
    best = sorted_sims[0]
    extras = sum(s * CHUNK_ATTENUATION for s in sorted_sims[1:])
    return min(best + extras, 1.0)


def hybrid_search(
    cards: Iterable[DocCard],
    query: str,
    embedding_results: list[EmbeddingResult] | None,
    *,
    project: str | None = None,
    type: str | None = None,
    type_boosts: dict[str, float] | None = None,
) -> list[SearchResult]:
    """Hybrid search combining stem matching and embedding similarity.

    If embedding_results is None (ChromaDB disabled), falls back to pure stem search
    with raw (unnormalized) scores for backward compatibility.

    Args:
        cards: Iterable of DocCards to search.
        query: Search query string.
        embedding_results: Results from embedding backend query, or None.
        project: Optional project filter.
        type: Optional document type filter.
        type_boosts: Optional dict of type_name -> multiplier.

    Returns:
        List of SearchResult sorted by relevance descending.
    """
    tokens = query.lower().split()
    if not tokens:
        return []

    # Phase 1: Stem search over all cards
    stem_scores: dict[str, float] = {}
    card_map: dict[str, DocCard] = {}

    for card in cards:
        if project is not None and card.project != project:
            continue
        if type is not None and card.type != type:
            continue
        card_map[card.doc_id] = card
        score = _score_card(card, tokens)
        if type_boosts and card.type:
            score *= type_boosts.get(card.type, 1.0)
        if score > 0:
            stem_scores[card.doc_id] = score

    # No embedding results — pure stem search with raw scores (backward compat)
    if embedding_results is None:
        results: list[SearchResult] = []
        for doc_id, raw_score in stem_scores.items():
            card = card_map[doc_id]
            results.append(
                SearchResult(
                    doc_id=doc_id,
                    project=card.project,
                    type=card.type,
                    filename=card.filename,
                    summary=card.summary,
                    keywords=card.keywords,
                    relevance=round(raw_score, 2),
                )
            )
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results

    # Phase 2: Process embedding results
    embed_scores: dict[str, float] = {}
    if embedding_results:
        # Group chunks by doc_id, filter by threshold
        doc_chunks: dict[str, list[float]] = {}
        for er in embedding_results:
            # Convert score back to distance for threshold check
            distance = (1.0 - er.score) * 2.0
            if distance > EMBED_DISTANCE_THRESHOLD:
                continue
            if er.doc_id not in card_map:
                continue
            doc_chunks.setdefault(er.doc_id, []).append(er.score)

        # Aggregate per document
        for doc_id, sims in doc_chunks.items():
            embed_scores[doc_id] = _aggregate_chunk_scores(sims)

    # Phase 3: Merge
    all_doc_ids = set(stem_scores.keys()) | set(embed_scores.keys())
    if not all_doc_ids:
        return []

    results = []
    for doc_id in all_doc_ids:
        card = card_map[doc_id]
        s_raw = stem_scores.get(doc_id, 0.0)
        s_norm = min(s_raw / STEM_NORMALIZER, 1.0)
        e_score = embed_scores.get(doc_id, 0.0)
        hybrid = s_norm * STEM_WEIGHT + e_score * EMBED_WEIGHT

        results.append(
            SearchResult(
                doc_id=doc_id,
                project=card.project,
                type=card.type,
                filename=card.filename,
                summary=card.summary,
                keywords=card.keywords,
                relevance=round(hybrid, 4),
            )
        )

    results.sort(key=lambda r: r.relevance, reverse=True)
    return results
