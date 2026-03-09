# PLAN — Bilingual Morphological Search (v0.5.0)

Task: `docs/ASTROLABE-SEARCH-001.md`

- [x] **1. Create PLAN.md + PROGRESS.md**
  - Action: создать трекинг файлы
  - Output: docs/PLAN.md, docs/PROGRESS.md

- [x] **2. Update spec (spec-first)**
  - Input: `docs/specs/spec_search.md` (Status: READY)
  - Action: Status → IN_PROGRESS. Stem matching, новые веса, убрать EXACT_BONUS, snowballstemmer
  - Output: spec_search.md с новым поведением
  - Checkpoint: спека соответствует ASTROLABE-SEARCH-001.md

- [x] **3. Add dependency, bump version**
  - Input: `pyproject.toml` (v0.4.0)
  - Action: `snowballstemmer>=2.0`, version → 0.5.0, install
  - Checkpoint: `python -c "import snowballstemmer"` ✓

- [x] **4. Rewrite search.py**
  - Input: spec, код из ASTROLABE-SEARCH-001.md
  - Action: стеммеры, новые веса, `_stems()`, stem intersection, filename split
  - Checkpoint: ruff + mypy clean

- [x] **5. Update tests + add morphological tests**
  - Input: `tests/test_search.py` (12 тестов)
  - Action: +4 теста (RU/EN morphology, filename split, weight ordering)
  - Checkpoint: 16 тестов зелёные

- [x] **6. Full quality checks**
  - Action: ruff + mypy + pytest — full suite
  - Checkpoint: ноль ошибок

- [x] **7. Update docs**
  - Action: spec → READY, ARCHITECTURE.md, README.md
  - Checkpoint: документация = реализация

