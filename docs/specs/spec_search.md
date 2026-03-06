# spec_search — Text Search

Status: READY

## Overview

Token-level text search over enriched DocCards with field weights.

## Public API

### `search(cards: Iterable[DocCard], query: str, *, project: str | None = None, type: str | None = None) -> list[SearchResult]`

Search enriched cards by query.

**Parameters:**
- `cards`: iterable of DocCard (typically `index.documents.values()`)
- `query`: search query string
- `project`: optional filter
- `type`: optional filter

**Returns:** list of SearchResult, sorted by relevance descending. Only cards with relevance > 0 are returned.

**Behavior:**
- Query is split into tokens (whitespace-separated, lowercased)
- Each token is searched in card fields with weights:
  - `keywords`: 3.0
  - `filename`: 2.5
  - `headings`: 2.0
  - `summary`: 1.0
- Matching: case-insensitive substring. Exact token match gets 1.5x bonus.
- Cards without enrichment (`enriched_at is None`) still match on `filename`.
- Relevance score is sum of all token-field matches.
- Filters (project, type) applied before scoring.

## Dependencies

- `astrolabe.models` (DocCard, SearchResult)
