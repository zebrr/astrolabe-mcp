# spec_search — Bilingual Morphological Search

Status: READY

## Overview

Bilingual stem-based search (EN + RU) over enriched DocCards with field weights.

## Public API

### `search(cards: Iterable[DocCard], query: str, *, project: str | None = None, type: str | None = None, type_boosts: dict[str, float] | None = None, date_from: str | None = None, date_to: str | None = None) -> list[SearchResult]`

Search enriched cards by query.

**Parameters:**
- `cards`: iterable of DocCard (typically `index.documents.values()`)
- `query`: search query string
- `project`: optional filter
- `type`: optional filter
- `type_boosts`: optional dict `type_name → multiplier` from doc_types.yaml
- `date_from`, `date_to`: optional YYYY-MM-DD bounds for `card.date` (inclusive). Cards with `date=None` are **excluded** when at least one bound is set.

**Returns:** list of SearchResult, sorted by relevance descending. Only cards with relevance > 0 are returned.

**Behavior:**
- Query is split into tokens (whitespace-separated, lowercased)
- Each token is stemmed with both EN and RU Snowball stemmers → `stems(token)` = set of 2 stems
- Each word in a field is stemmed the same way → `stems(word)` = set of 2 stems
- Token matches a word if `stems(token) ∩ stems(word) ≠ ∅`
- `filename` is split on `_`, `-`, `.` before word-level matching
- Field weights:
  - `keywords`: 3.0
  - `headings`: 2.0
  - `summary`: 1.5
  - `filename`: 0.8
- No exact bonus (removed — stem match already handles it)
- Cards without enrichment (`enriched_at is None`) still match on `filename`
- Relevance score is sum of all token-field matches
- Filters (project, type, date_from, date_to) applied before scoring
- Date bounds use lexicographic string comparison (safe because `YYYY-MM-DD` is lexicographically chronological)

### `hybrid_search(...)` extends the signature with the same `date_from` / `date_to` parameters.

Date filtering applies in both the stem and embedding phases (an embedding match is ignored if the corresponding card fails the date filter).

## Dependencies

- `astrolabe.models` (DocCard, SearchResult)
- `snowballstemmer` (English + Russian stemmers)
