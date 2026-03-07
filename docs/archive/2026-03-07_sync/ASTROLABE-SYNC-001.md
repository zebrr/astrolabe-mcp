# ASTROLABE-SYNC-001: Cross-Platform Index Sync

## References
- `docs/CONCEPT.md` — концепция, архитектура индекса, MCP tools
- `docs/ARCHITECTURE.md` — структура модулей, зависимости
- `src/astrolabe/index.py` — `_compute_hash()`, `reindex()`, `ReindexStats`
- `src/astrolabe/models.py` — `AppConfig`, `DocCard`, `IndexData`, `CosmosResponse`
- `src/astrolabe/server.py` — MCP tools (`reindex_tool`, `get_cosmos`)
- `runtime/config.example.json` — шаблон конфига
- `README.md` — пользовательская документация

## Context

Astrolabe используется кросс-платформенно (Windows + Mac). Индекс `.doc-index.json` платформо-независим по структуре (rel_path в POSIX, doc_id как `project::rel_path`), но есть проблемы при синхронизации одного индекса между машинами.

Сценарий: индекс хранится в облачной папке (Google Drive / OneDrive), `index_path` в конфиге указывает туда абсолютным путём. Конфиг gitignored, на каждой машине свой.

Цель: сделать этот сценарий полностью рабочим.

## Steps

### 1. Нормализация хеша (index.py)

**Проблема:** `_compute_hash()` считает MD5 от `read_bytes()`. Git на Windows с `core.autocrlf=true` хранит файлы с CRLF в working directory. На Mac — LF. Один и тот же файл даёт разные хеши → карточка ложно помечается stale.

**Решение:** нормализовать line endings перед хешированием — `raw.replace(b'\r\n', b'\n')` перед MD5.

**Важно:** это меняет хеши всех существующих карточек. После деплоя нужен `reindex()` — все файлы будут помечены как stale (хеш не совпадёт со старым), но enrichment сохранится. Одноразовая миграция.

### 2. Partial config — pass-through чужих проектов (index.py) [CRITICAL]

**Проблема:** индекс общий, но на разных машинах в конфиге могут быть разные наборы проектов (не все репы склонированы везде). Сейчас `reindex()` считает карточки из неизвестных проектов **removed** и удаляет их. Первый же reindex на "неполной" машине убьёт enrichment по отсутствующим проектам.

Конкретно вот этот блок:
```python
# Removed files
for doc_id in existing.documents:
    if doc_id not in fresh_cards:
        stats.removed += 1
```

**Решение:** `reindex()` должен различать:
- Карточка из проекта, который **есть в конфиге** → файл реально удалён → removed
- Карточка из проекта, которого **нет в конфиге** → pass-through, сохранить as-is

Для этого достаточно проверять `card.project in config.projects`. Карточки чужих проектов копируются в новый индекс без изменений.

`ReindexStats` — добавить `passthrough: int = 0` для прозрачности.

### 3. Детекция недосинка (index.py, models.py, server.py)

**Проблема:** при работе через облачный индекс возможна ситуация: кэш обогащён на одной машине, но git не подтянут на другой. Файл в кэше новее, чем на диске, или есть в кэше, но отсутствует на диске.

**Логика трёх состояний:**

| Ситуация | Значит | Тип |
|---|---|---|
| `file.modified > card.enriched_at` | Файл обновился → переобогатить | stale (уже есть) |
| `card.enriched_at > file.modified` | Кэш из будущего → git pull нужен | **desync** (новое) |
| Карточка есть, файла на диске нет | Файл не подтянут | **desync** (новое) |

**Изменения:**

- `ReindexStats` — добавить поле `desync: int = 0`
- `reindex()` — при обнаружении desync-ситуаций:
  - НЕ удалять карточку (как сейчас при removed)
  - Сохранить карточку, инкрементировать `stats.desync`
  - Опционально: добавить флаг `desync: bool` в `DocCard` или определять динамически
- `CosmosResponse` — добавить `desync_documents: int`
- `get_cosmos()` — возвращать desync-статистику

Агент при старте сессии видит `desync: 3` и предупреждает: "3 файла в индексе новее локальных или отсутствуют. Возможно, нужен git pull в проектах X, Y."

### 4. Force reindex (index.py, server.py)

**Проблема:** `reindex()` всегда сохраняет enrichment. Иногда нужен полный сброс (сломанный индекс, массовое переименование, смена типизации).

**Решение:** параметр `force` в `reindex()` и `reindex_tool`:

- `reindex()` / `reindex(force=False)` — текущее поведение, merge с сохранением enrichment. `force` дефолтно `False`, backward compatible
- `reindex(force=True)` — чистый скан с нуля, все карточки пустые (по сути `build_index()`). Карточки чужих проектов — pass-through
- `reindex(project="x", force=True)` — сброс enrichment только для одного проекта

### 5. Документация (config.example.json, README.md)

**config.example.json** — добавить комментарий/пример про облачный путь:
```json
{
  "index_path": ".doc-index.json",
  "_index_path_note": "For cross-platform sync, use absolute path to cloud folder, e.g. G:/My Drive/astrolabe/.doc-index.json (Win) or /Volumes/GoogleDrive/My Drive/astrolabe/.doc-index.json (Mac)"
}
```

**README.md** — секция "Cross-Platform Sync":
- Объяснить сценарий: один индекс в облаке, по конфигу на каждой машине
- Нормализация хешей обеспечивает совместимость
- Детекция недосинка предупреждает про git pull
- Конфиг gitignored → разные пути на разных платформах, это by design

### 6. Version Update

Обновить (везде) версию приложения 0.2.0 → 0.2.1

## Testing

### Нормализация хеша
- Создать temp-файл с `\r\n`, проверить что хеш совпадает с `\n`-версией
- Проверить что бинарные файлы (если попадут) не ломаются от замены

### Partial config (pass-through)
- Индекс с карточками из проектов A, B, C. Конфиг содержит только A, B
- `reindex()` → карточки C сохранены as-is, `stats.passthrough` корректен
- Карточки A, B обработаны нормально (new/stale/unchanged/removed)
- Удалённый файл из проекта A → removed. Карточка из проекта C без файла → passthrough (НЕ removed)

### Детекция недосинка
- Карточка с `enriched_at` в будущем относительно `modified` → desync
- Карточка есть в индексе, файла нет на диске, проект в конфиге → desync (не removed)
- `get_cosmos()` возвращает `desync_documents`
- `ReindexStats` содержит корректный `desync` count

### Force reindex
- `reindex(force=True)` — сброс enrichment только по проектам из конфига, чужие — passthrough (force не убивает чужое)
- `reindex(project="x", force=True)` — только проект x сброшен, остальные intact
- `reindex()` / `reindex(force=False)` — поведение не изменилось (backward compatible)

## Deliverables
- Версия приложения обновлена везде (0.2.0 не находится)
- Обновлённые: `index.py`, `models.py`, `server.py`
- Обновлённые: `config.example.json`, `README.md`
- Новые/обновлённые тесты
- Все существующие тесты проходят (`pytest -v`)
- Отчет написан `ASTROLABE-SYNC-001_REPORT.md`