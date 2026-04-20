# PROGRESS — v0.10.0: Optional `date` field

## Status

COMPLETED

## Current State

Работа над фичей: опциональное поле `date` (YYYY-MM-DD) на карточке документа. Скилл `enrich-index` будет извлекать дату из содержимого (шапка/конец документа для справок, выписок, отчётов). Фильтрация по диапазону и сортировка в `list_docs`/`search_docs`. Счётчик `dated_documents` в `get_cosmos`.

## Decisions

- **Формат строго YYYY-MM-DD** — частичные даты (YYYY-MM, YYYY) не поддерживаем. Простая валидация и однозначная сортировка. Если в документе дата неполная — не заполняем.
- **Диапазон дат в документе → end date**. Для справки/выписки актуальность определяется по конечной дате. Пользователь подтвердил при планировании.
- **API фильтра: `date_from` + `date_to` (inclusive)** вместо date_prefix. Покрывает все сценарии; пара параметров — стандартный паттерн.
- **Sort-параметр отдельный** (`sort="date_desc"`/`date_asc"`/`relevance`) — не смешиваем с фильтром. Карточки с `date=None` идут в конец при сортировке, исключаются при фильтре.
- **Ответы тулов не эмитят `date=None`** — паттерн уже есть для `diverged_from`, `has_copies`. Минимизирует шум.
- **Валидация формата в `update_index_tool`** — regex `^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$`. Возвращаем error dict (как при bad type), не raise.
- **Web UI (`src/astrolabe/web/`) — added in same milestone** (step 11): просмотр и редактирование поля date в карточке, без фильтров/сортировок в списке и поиске.
- **Clear semantics унифицировано с API**: `""` в `update_card` / `update_index_tool` = очистить поле; `None` = не трогать; валидная `YYYY-MM-DD` = установить. Это открывает симметричный путь из Web UI и из MCP-тула. Валидатор формата пропускает пустую строку.
- **Backfill существующих карточек не автоматизируем** — пользователь сам инициирует enrich-skill когда нужно.
- **Clear date API нет** — паттерн общий для всех enrichment-полей (update_card не умеет обнулять summary/keywords).

---

## Events

### E001 — 2026-04-20 15:37 — Plan approved, milestone started

Approved plan at `~/.claude/plans/typed-prancing-dove.md`. Creating PLAN.md and PROGRESS.md as Step 0 of planned work. Version target: 0.10.0 (minor bump, backward-compatible feature).

### E002 — 2026-04-20 15:49 — Milestone complete

All 10 steps done. Field `date: str | None` added to DocCard with strict `YYYY-MM-DD` validation at the tool layer. SQLite schema extended via ALTER TABLE (legacy DBs load with date=None). `update_card()` preserves date on file-change reindex and move auto-transfer. `search()` / `hybrid_search()` filter by `date_from` / `date_to`. `list_docs` / `search_docs` support sort by date (undated → end). `get_card` includes date when set. `get_cosmos` exposes `dated_documents` + per-project `dated_count`. `enrich-index` skill gained an "Extracting Date" section with range→end-date rule and YYYY-MM-DD format enforcement.

**Final checks:** 399 tests passed; `ruff check`, `ruff format`, `mypy src/` clean. Version bumped to 0.10.0. ARCHITECTURE.md updated with the new decision entry. All specs back to READY.

**Post-install note:** reinstall the package (`pip install -e .`) and restart the MCP server to pick up new tool signatures.

### E003 — 2026-04-20 16:38 — Web UI reopened for date view/edit

User tested v0.10.0 via MCP (set date on an archive PROGRESS.md, filter + sort worked as expected). Web UI was marked out of scope in E002 but is small enough to fold into the same milestone. New step 11 added to PLAN.md — view/edit date in card partial, reuse regex validator, unify clear semantics across Web + API (`""` = clear, `None` = untouch, `YYYY-MM-DD` = set). Version stays 0.10.0 — not released yet.

### E004 — 2026-04-20 16:42 — Step 11 done

Shared `DATE_RE` moved from `server.py` into `models.py` so Web UI can reuse it. `update_card` (index.py) and `update_index_tool` (server.py) now accept `""` as an explicit clear sentinel; existing format validation passes an empty string through. `state.do_update_card` takes a tri-state `date`, and `routes_api.card_save` adds a `date` form field — invalid format returns a toast error, empty value clears. Template `partials/card_fields.html` gained a `<input type="date">` in edit mode and a view-mode row. Specs updated (spec_models, spec_server, spec_web). 406 tests passed (7 new for clear/web roundtrip); ruff, mypy clean. No version change — still 0.10.0 pre-release.
