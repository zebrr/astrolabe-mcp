# ASTROLABE-SEARCH-001: Bilingual Morphological Search

## References

- `src/astrolabe/search.py` — current implementation
- `docs/specs/spec_search.md` — spec to update (Status: READY → IN_PROGRESS → READY)
- `tests/test_search.py` — test suite to update
- `pyproject.toml` — dependencies and version

## Context

Current search is token-level substring matching with field weights. Works fine for exact
tokens but misses morphological variants: "бегущий" won't find "бежать", "running" won't
find "run". Goal is to add bilingual stemming (RU + EN) via `snowballstemmer` and rebalance
field weights now that filename substring hacks are no longer needed.

## Steps

### 1. Add dependency

In `pyproject.toml`:
- Add `snowballstemmer>=2.0` to `dependencies`
- Bump version: `0.4.0` → `0.5.0`

### 2. Update `spec_search.md`

Replace the Behavior section with:

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
- Filters (project, type) applied before scoring

Mark spec Status → READY when done.

### 3. Rewrite `search.py`

**Module-level:**
```python
import snowballstemmer

_stemmer_en = snowballstemmer.stemmer("english")
_stemmer_ru = snowballstemmer.stemmer("russian")

FIELD_WEIGHTS: dict[str, float] = {
    "keywords": 3.0,
    "headings": 2.0,
    "summary":  1.5,
    "filename": 0.8,
}

# Remove EXACT_BONUS entirely
```

**New helper `_stems(word: str) -> frozenset[str]`:**
```python
def _stems(word: str) -> frozenset[str]:
    w = word.lower()
    return frozenset([
        _stemmer_en.stemWord(w),
        _stemmer_ru.stemWord(w),
    ])
```

**Rewrite `_score_token_in_field(token: str, field_value: str) -> float`:**
```python
def _score_token_in_field(token: str, field_value: str) -> float:
    token_stems = _stems(token)
    words = field_value.lower().split()
    for word in words:
        if token_stems & _stems(word):
            return 1.0
    return 0.0
```

**Update `_score_card`** — filename needs word splitting before scoring:
```python
# filename — split on _, -, . then score word by word
filename_as_text = card.filename.replace("_", " ").replace("-", " ").replace(".", " ")
s = _score_token_in_field(token, filename_as_text)
score += s * FIELD_WEIGHTS["filename"]
```

Everything else in `_score_card` stays structurally the same (keywords loop, headings loop,
summary) — just uses new `_score_token_in_field`.

### 4. Update `test_search.py`

- Update `test_keywords_weighted_higher` — the ordering assertion stays valid but check
  it still holds with new weights
- Update `test_sorted_by_relevance` — same
- Remove or update any test that relied on `EXACT_BONUS` behavior
- Add morphological tests:

```python
def test_ru_morphology(self) -> None:
    """Russian stemming: query stem matches card stem."""
    cards = [_card(keywords=["индексирование"], enriched=True)]
    results = search(cards, "индексация")
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
```

### 5. Quality checks

```bash
pip install snowballstemmer  # or: uv pip install snowballstemmer
ruff check src/ tests/
mypy src/
pytest -v
```

All checks must be green before marking done.

## Testing

```bash
pytest tests/test_search.py -v
```

Expected: all existing tests pass + 4 new morphological tests pass.

Quick smoke test after install:
```python
import snowballstemmer
en = snowballstemmer.stemmer("english")
ru = snowballstemmer.stemmer("russian")
assert en.stemWord("running") == en.stemWord("run")       # True
assert ru.stemWord("индексирование") == ru.stemWord("индексации")  # should be same stem
```

## Deliverables

- `src/astrolabe/search.py` — rewritten with bilingual stemming, new weights, no EXACT_BONUS
- `docs/specs/spec_search.md` — updated, Status: READY
- `tests/test_search.py` — updated + 4 new tests, all green
- `pyproject.toml` — `snowballstemmer` dependency, version `0.5.0`
