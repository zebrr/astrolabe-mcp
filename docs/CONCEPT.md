# Astrolabe' Knowledge Layer MCP — Концепция

> Название: **astrolabe-mcp**
> Статус: актуален
> Дата: 2026-03-07

## Проблема

Работаем с несколькими проектами параллельно. В каждом проекте есть документация, и между проектами много пересечений:

- **Проектные инструкции** — на 80% одинаковые, с уникальными частями
- **CLAUDE.md** — специфичные для каждого проекта
- **Рефы** (references) — часто копии одного и того же, раскиданные по проектам
- **Таски и отчёты** — уникальные, но единый формат
- **Спеки** — уникальные, но близкий формат и общая инструкция по написанию
- **Скиллы** — паттерны и инструкции в `.claude/`, `.qwen/`, `skills_drafts/`
- **Утилиты** — служебные скрипты, конвертеры, переиспользуемые между проектами
- **Проектная документация** — README, архитектура, манифесты

Боли:
- Копирование рефов и утилит между проектами вручную
- Claude Code не видит файлы за пределами своего проекта
- Claude App требует настройки filesystem-доступов
- Нет единой точки поиска "есть ли у нас реф по X?"
- Нет способа найти "как мы это делали раньше" across projects
- Полезные скрипты теряются или дублируются

## Решение

MCP-сервер, который создаёт **прозрачный knowledge layer** поверх всех проектов. Единая точка доступа к документации для любого агента через стандартные MCP tools.

### Принципы

1. **Проекты не трогаем** — никакого frontmatter, никаких изменений в файлах проектов. Вся метаинформация живёт в индексе MCP-сервера
2. **MCP-сервер тупой** — он умеет только обходить файлы, хранить индекс, отдавать содержимое. Никакого LLM, никакой классификации, никакого парсинга. Чистый Python, минимум зависимостей
3. **Интеллект на стороне агента** — агент читает файлы, понимает их, обогащает карточки индекса через `update_index()`. Агент — это и есть LLM, который уже оплачен и в контексте
4. **Progressive disclosure** — агент сначала видит каталог карточек, потом осознанно читает нужный файл. Как активация скиллов — описание → решение → чтение
5. **Управляемая типизация** — фиксированный набор типов в `doc_types.yaml`. Всё, что не определилось — `undef`. Новые типы вводятся осознанно, после анализа `undef`-карточек
6. **Кросс-платформенность** — индекс хранит только `rel_path`, абсолютные пути собираются из конфига. Работает на Windows и Mac без изменений
7. **Мультиклиентность** — один MCP-сервер, много клиентов: Claude Code, Claude App, Codex, External API-бот, что угодно с поддержкой MCP
8. **MVP — чтение + обогащение индекса** — запись файлов (создание тасков, обновление рефов) откладывается на следующие итерации

## Что делает пользователь (один раз)

### Конфиг проектов (`config.json`)

Пользователь работает параллельно под Win/Mac, возможно, нужно два конфига либо он должен быть платформо-агностичен. Например, поддерживать оба варианта путей и при старте загружать только необходимые.

```json
{
  "projects": {
    "project-a": "/path/to/project-a",
    "project-b": "/path/to/project-b",
    "project-c": "/path/to/project-c"
  },
  "index_path": ".doc-index.json",
  "index_extensions": [".md", ".yaml", ".yml", ".txt", ".py", ".sh"],
  "ignore_dirs": [
    "src", "lib", "app", "tests", "test",
    "dist", "build", "node_modules", ".venv", "venv",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    ".git", ".idea", ".vscode", ".claude",
    "tmp", "temp"
  ],
  "ignore_files": ["*.pyc", "*.lock", ".env*"],
  "max_file_size_kb": 100
}
```

**Что индексируем:** документацию (`.md`, `.yaml`, `.yml`, `.txt`), утилиты и скрипты (`.py`, `.sh`). Также поддерживаются бинарные файлы (`.pdf`, `.docx`, медиа) — индексируются по метаданным.

**Что исключаем:** `ignore_dirs` — имена директорий (не пути), пропускаются на любой глубине. `ignore_files` — glob-паттерны для файлов. `max_file_size_kb` — лимит для полного чтения через `read_doc()`.

**`index_path`** — путь к индексу. Для кросс-платформенной синхронизации можно указать абсолютный путь к облачной папке (Google Drive, OneDrive).

### Мягкая типизация (`doc_types.yaml`)

Описание типов для агента — не жёсткие правила, а ориентир. Агент при обогащении карточки сам решает, какой тип назначить, опираясь на содержимое файла и эти описания.

```yaml
document_types:

  instruction:
    description: >
      Проектная инструкция, правила работы агента. Определяет как работать
      в проекте, какие есть ограничения, какой workflow. Обычно CLAUDE.md
      или PROJECT.md в корне проекта.

  reference:
    description: >
      Справочный материал по API, инструменту, подходу, методологии.
      Содержит примеры вызовов, параметры, ограничения.

  task:
    description: >
      Рабочее задание для агента. Содержит контекст, шаги, критерии
      проверки, ожидаемые результаты.

  report:
    description: >
      Отчёт о выполнении задания. Содержит что сделано, что изменено,
      результаты тестов.

  spec:
    description: >
      Техническая спецификация, архитектура, дизайн-документ.
      Описывает как устроена система или модуль.

  document:
    description: >
      Концепция, архитектура, README, ключевые проектные договорённости.
      Документы для совместной работы между пользователем и агентом.

  skill:
    description: >
      Навык (skill) агента — инструкция, паттерн, алгоритм работы.
      Содержит когда применять, как выполнять, примеры.

  utility:
    description: >
      Служебный скрипт, конвертер, утилита — переиспользуемый инструмент.

  project_state:
    description: >
      План, прогресс, changelog, todo — текущее состояние проекта.

  binary_doc:
    description: >
      PDF, Word, Excel, PowerPoint. Индексируются по метаданным и имени файла.

  media:
    description: >
      Изображения, аудио, видео. Индексируются по метаданным и имени файла.

  undef:
    description: >
      Файл не подходит ни под один тип. Всегда указывать в summary что содержит.
```

**Набор типов фиксирован** в `doc_types.yaml`. Агент при обогащении использует только определённые типы. Если файл не подходит ни под один — присваивается `undef`. Периодически `undef`-карточки анализируются и при необходимости вводятся новые типы.

## Индексация

### Архитектура: тупой сервер + умный агент

MCP-сервер НЕ содержит никакого LLM, НЕ классифицирует файлы, НЕ генерирует описания. Он только:
- Обходит файлы в проектах
- Хранит индекс (файловые метаданные + карточки)
- Отдаёт данные через tools
- Принимает обогащённые карточки от агентов

Вся классификация и генерация описаний — на стороне агента (CC, Claude App, любой LLM-клиент).

### Жизненный цикл индекса

**1. Старт MCP → "голый" индекс**

При старте сервер обходит все проекты из конфига и для каждого файла с подходящим расширением создаёт запись с файловыми метаданными. Карточки пустые (type, summary, keywords, headings — null).

**2. Первичное обогащение → агент заполняет карточки**

Агент (CC или любой другой) вызывает `list_docs(project)` → видит файлы без описаний → читает через `read_doc()` → думает → вызывает `update_index(doc_id, type, summary, keywords, headings)`. Постепенно, файл за файлом. Типы документов берёт из `doc_types.yaml` как ориентир, но может назначить любой тип.

**Вопрос:** Нужны ли headings? Summary — да, keywords — тоже да, а что будет в headings?

**3. Рутинная работа → точечное обновление**

Агент отредактировал документ → сам вызывает `update_index()` для него. Или периодически: `list_docs(stale=true)` → обогащение устаревших карточек.

**4. Глобальный reindex → обновление только файловых метаданных**

`reindex()` пересканирует файловую систему: обновляет size, modified, content_hash, добавляет новые файлы. **Карточки (type, summary, keywords, headings) НЕ трогает.** Если файл изменился (content_hash не совпадает) — карточка помечается как stale, но не стирается.

Особые случаи:
- **Pass-through:** карточки из проектов, которых нет в текущем конфиге, сохраняются без изменений (для кросс-платформенной синхронизации)
- **Desync:** если файл отсутствует на диске, но проект есть в конфиге — карточка сохраняется (файл может быть не подтянут через git). Также desync фиксируется, когда `enriched_at > modified` (обогащение пришло с другой машины)
- **Force:** `reindex(force=True)` — чистый скан с нуля, enrichment сбрасывается. Desync-карточки удаляются. Pass-through сохраняется
- **Хеш-нормализация:** `content_hash` вычисляется после нормализации CRLF→LF для кросс-платформенной совместимости

### Формат индекса (`.doc-index.json`)

```json
{
  "version": "0.2.1",
  "indexed_at": "2026-03-07T12:00:00Z",
  "documents": {
    "web-app::docs/references/API Reference.md": {
      "project": "web-app",
      "filename": "API Reference.md",
      "rel_path": "docs/references/API Reference.md",
      "size": 4200,
      "modified": "2025-12-15T10:30:00Z",
      "content_hash": "a1b2c3...",
      "type": "reference",
      "headings": ["Установка", "Конфигурация", "Форматирование Formatting"],
      "summary": "Справочник по работе с External API через MCP: настройка клиента, форматирование, лимиты API",
      "keywords": ["api", "bot", "mcp", "formatting", "endpoints"],
      "enriched_at": "2026-03-07T12:05:00Z"
    },
    "data-lib::docs/System Architecture.md": {
      "project": "data-lib",
      "filename": "System Architecture.md",
      "rel_path": "docs/System Architecture.md",
      "size": 12800,
      "modified": "2025-11-20T14:00:00Z",
      "content_hash": "d4e5f6...",
      "type": null,
      "headings": null,
      "summary": null,
      "keywords": null,
      "enriched_at": null
    }
  }
}
```

Ключевые поля:
- `modified` — дата изменения файла (из файловой системы)
- `enriched_at` — дата последнего обогащения карточки агентом
- Карточка считается **stale** если `modified > enriched_at` (файл изменился после последнего обогащения)
- Карточка считается **empty** если `enriched_at == null` (ни разу не обогащалась)

## MCP Tools (MVP)

### `get_cosmos()`

Точка входа. Возвращает полный каталог — проекты, доступные типы документов, статус индекса. Агент вызывает это в начале сессии и получает всё, что нужно для осмысленных запросов к остальным tools.

**Параметры:** нет

**Возвращает:**
```json
{
  "server_version": "0.2.1",
  "indexed_at": "2026-03-07T12:00:00Z",
  "total_documents": 48,
  "enriched_documents": 35,
  "stale_documents": 4,
  "empty_documents": 9,
  "desync_documents": 2,
  "projects": [
    {
      "id": "web-app",
      "doc_count": 24,
      "enriched_count": 20,
      "last_indexed": "2026-03-07T12:00:00Z"
    },
    {
      "id": "data-lib",
      "doc_count": 10,
      "enriched_count": 8,
      "last_indexed": "2026-03-07T12:00:00Z"
    }
  ],
  "document_types": [
    {"type": "document", "description": "Концепция, архитектура, README", "count": 4},
    {"type": "instruction", "description": "Проектная инструкция, правила работы агента", "count": 5},
    {"type": "reference", "description": "Справочный материал по API, инструменту, подходу", "count": 8},
    {"type": "spec", "description": "Техническая спецификация, архитектура", "count": 5},
    {"type": "task", "description": "Рабочее задание для агента", "count": 12},
    {"type": "report", "description": "Отчёт о выполнении задания", "count": 7},
    {"type": "skill", "description": "Навык агента — инструкция, паттерн, алгоритм", "count": 6}
  ]
}
```

**Примечания:**
- `document_types` строится из реального индекса (только типы, которые реально назначены), а не из `doc_types.yaml`
- `enriched_documents` / `stale_documents` / `empty_documents` — статистика покрытия индекса
- `desync_documents` — файлы, отсутствующие локально или обогащённые на другой машине
- Агент сразу видит: 9 файлов без описания, 4 устарели, 2 в десинке — можно предложить обогащение или git pull

**Когда вызывать:** начало сессии.

---

### `list_docs(project?, type?, stale?)`

Список карточек документов с фильтрами.

**Параметры:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| project | string | нет | Фильтр по проекту |
| type | string | нет | Фильтр по типу документа |
| stale | bool | нет | `true` — только stale/empty карточки (modified > enriched_at или enriched_at == null) |

**Возвращает:** массив карточек
```json
[
  {
    "doc_id": "web-app::docs/references/API Reference.md",
    "project": "web-app",
    "type": "reference",
    "filename": "API Reference.md",
    "summary": "Справочник по работе с External API через MCP...",
    "keywords": ["api", "bot", "mcp"],
    "modified": "2025-12-15T10:30:00Z",
    "enriched_at": "2026-03-07T12:05:00Z"
  }
]
```

**Когда вызывать:** обзор проекта, просмотр всех рефов, поиск устаревших карточек для обогащения.

---

### `search_docs(query, project?, type?)`

Поиск документов по обогащённым карточкам. Ищет по filename + headings + summary + keywords. Возвращает только карточки с непустыми описаниями (обогащённые).

**Параметры:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| query | string | да | Поисковый запрос |
| project | string | нет | Фильтр по проекту |
| type | string | нет | Фильтр по типу документа |

**Возвращает:** массив карточек, отсортированных по relevance
```json
[
  {
    "doc_id": "web-app::docs/references/API Reference.md",
    "project": "web-app",
    "type": "reference",
    "filename": "API Reference.md",
    "summary": "Справочник по работе с External API через MCP...",
    "keywords": ["api", "bot", "mcp"],
    "relevance": 0.95
  }
]
```

**Примечание:** `search_docs` работает только по обогащённым карточкам. Необогащённые файлы можно найти через `list_docs(stale=true)`, но не через search — у них нет описаний для поиска. Поиск по filename работает для всех файлов.

**Когда вызывать:** "есть ли у нас реф по X?", "найди таски по digest", "как мы это делали раньше".

---

### `get_card(doc_id)`

Карточка индекса — метаданные и описание документа. Без содержимого файла.

**Параметры:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| doc_id | string | да | ID документа (формат `project::rel_path`) |

**Возвращает:**
```json
{
  "doc_id": "web-app::docs/references/API Reference.md",
  "project": "web-app",
  "filename": "API Reference.md",
  "rel_path": "docs/references/API Reference.md",
  "size": 4200,
  "modified": "2025-12-15T10:30:00Z",
  "type": "reference",
  "headings": ["Установка", "Конфигурация", "Форматирование Formatting"],
  "summary": "Справочник по работе с External API через MCP...",
  "keywords": ["api", "bot", "mcp", "formatting", "endpoints"],
  "enriched_at": "2026-03-07T12:05:00Z"
}
```

**Когда вызывать:** посмотреть полную карточку конкретного документа перед чтением.

---

### `read_doc(doc_id, section?, range?)`

Содержимое файла. Целиком, секция по заголовку, или диапазон строк.

**Параметры:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| doc_id | string | да | ID документа (формат `project::rel_path`) |
| section | string | нет | Заголовок секции — вернуть только эту часть |
| range | string | нет | Диапазон строк, например "1-50" |

**Возвращает:**
```json
{
  "doc_id": "web-app::docs/references/API Reference.md",
  "content": "# API Reference\n\n## Установка\n...",
  "total_lines": 180,
  "returned_lines": 180
}
```

Если указан `section`:
```json
{
  "doc_id": "web-app::docs/references/API Reference.md",
  "section": "Форматирование Formatting",
  "content": "## Форматирование Formatting\n...",
  "total_lines": 180,
  "returned_lines": 35
}
```

**Когда вызывать:** после `get_card` или `search_docs`, когда агент решил что нужно содержимое.

---

### `update_index(doc_id, type?, summary?, keywords?, headings?)`

Агент обогащает карточку индекса. Обновляет только переданные поля, остальные не трогает. Устанавливает `enriched_at` на текущее время.

**Параметры:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| doc_id | string | да | ID документа |
| type | string | нет | Тип документа (из `doc_types.yaml` или новый) |
| summary | string | нет | Краткое описание (2-3 предложения) |
| keywords | string[] | нет | Ключевые слова для поиска |
| headings | string[] | нет | Заголовки из документа |

**Возвращает:**
```json
{
  "doc_id": "data-lib::docs/System Architecture.md",
  "status": "updated",
  "enriched_at": "2026-03-07T12:10:00Z",
  "updated_fields": ["type", "summary", "keywords", "headings"]
}
```

**Когда вызывать:** после чтения файла через `read_doc()` — агент понял содержимое и заполняет карточку. Также после редактирования файла — обновить описание.

---

### `reindex(project?, force?)`

Пересканирование файловой системы. Обновляет файловые метаданные (size, modified, content_hash, новые файлы). По умолчанию **карточки (type, summary, keywords, headings) НЕ трогает.** Изменённые файлы помечает как stale. Отсутствующие файлы сохраняет как desync (не удаляет).

С `force=True` — чистый скан: enrichment сбрасывается, desync-карточки удаляются. Pass-through карточки (чужие проекты) сохраняются в любом случае.

**Параметры:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| project | string | нет | Пересканировать только указанный проект |
| force | bool | нет | Сбросить enrichment для настроенных проектов (default false) |

**Возвращает:**
```json
{
  "scanned": 52,
  "new": 2,
  "removed": 0,
  "stale": 4,
  "unchanged": 45,
  "passthrough": 3,
  "desync": 1,
  "duration_ms": 350
}
```

**Когда вызывать:** после создания/удаления файлов; при подозрении на устаревший индекс; `force=True` — после массовых переименований или при сломанном индексе.

## Типичные сценарии использования

### Сценарий 1: Начало сессии
```
Agent → get_cosmos()
MCP   → {projects: [5], document_types: [8], total: 48, stale: 4, empty: 9}
Agent → Знаю карту. 9 файлов без описания, 4 устарели.
```

### Сценарий 2: "Есть ли у нас реф по X?"
```
Agent → search_docs(query="api api")
MCP   → [{doc_id: "web-app::...", type: "reference", summary: "..."}]
Agent → Да, есть. Нужно содержимое?
Agent → read_doc(doc_id="web-app::docs/references/API Reference.md")
```

### Сценарий 3: "Как мы это делали раньше?"
```
Agent → search_docs(query="API migration", type="report")
MCP   → [{doc_id: "web-app::docs/tasks/PROJ-FEAT-003_REPORT.md", ...}]
Agent → read_doc("web-app::docs/tasks/PROJ-FEAT-003_REPORT.md")
```

### Сценарий 4: Контекст из другого проекта
```
Agent → search_docs(query="data pipeline")
MCP   → [{doc_id: "data-lib::docs/System Architecture.md", ...}]
Agent → read_doc("data-lib::docs/System Architecture.md", section="Data Processing")
```

### Сценарий 5: Первичное обогащение
```
Agent → list_docs(project="my-project", stale=true)
MCP   → [{doc_id: "my-project::README.md", type: null, summary: null}, ...]
Agent → read_doc("my-project::README.md")
Agent → [читает, думает]
Agent → update_index("my-project::README.md",
          type="document",
          summary="Project overview and quick start guide...",
          keywords=["agent", "framework", "autonomous"],
          headings=["Architecture", "Quick Start", "Configuration"])
```

### Сценарий 6: Обновление после редактирования
```
Agent → [отредактировал docs/references/API Reference.md]
Agent → update_index("web-app::docs/references/API Reference.md",
          summary="Обновлённый справочник...",
          keywords=["api", "bot", "mcp", "formatting", "new-endpoint"])
```

### Сценарий 7: Поиск устаревших описаний
```
Agent → list_docs(stale=true)
MCP   → [{doc_id: "web-app::CLAUDE.md", modified: "2026-03-06", enriched_at: "2026-02-20"}, ...]
Agent → Файл обновлён, описание устарело. Перечитаю и обновлю.
```

## Мультиклиентность

MCP — стандартный протокол. Сервер один, клиентов сколько угодно:

- **Claude Code** — подключается через `.mcp.json`, поиск и чтение рефов из других проектов
- **Claude App** — подключается через `claude_desktop_config.json`, стратегический обзор
- **Codex / другие агенты** — любой MCP-совместимый клиент подключается аналогично
- **External API-бот** — импортирует core-модуль напрямую или через MCP-клиент. Сценарий: "реф по External API API" → карточка → секция

### Архитектура: core + transport

Для мультиклиентности стоит разделить:
- **Core** — индексация, поиск, чтение, хранение. Чистый Python, без зависимости от MCP
- **Transport: MCP** — обёртка core в MCP tools через stdio. Для агентов
- **Transport: HTTP** (будущее) — REST API поверх core. Для бота и других клиентов
- **Transport: CLI** (будущее) — командная строка. Для быстрых проверок

## Технический стек

- **Язык:** Python 3.11+
- **MCP SDK:** `mcp` (официальный Python SDK от Anthropic)
- **Транспорт:** stdio (стандартный для локальных MCP-серверов)
- **Индекс:** JSON-файл (`.doc-index.json`), при росте — SQLite
- **Зависимости:** минимум (только `mcp` SDK)

**Вопрос:** Сможем ли мы потом транспорт расширить и на HTTP/CLI?

### Почему Python

- Естественная экосистема для работы с файлами, парсингом, индексацией
- Если потом захотим эмбеддинги — `sentence-transformers`, `numpy`, `faiss` нативно
- MCP Python SDK зрелый
- Консистентно с остальными проектами

## Подключение

### Claude Code (`~/.claude/settings.json` или project `.mcp.json`)
```json
{
  "mcpServers": {
    "astrolabe": {
      "command": "python",
      "args": ["path/to/astrolabe-mcp/server.py"],
      "env": {
        "ASTROLABE_CONFIG": "path/to/astrolabe-mcp/config.json"
      }
    }
  }
}
```

### Claude App (Claude Desktop `claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "astrolabe": {
      "command": "python",
      "args": ["path/to/astrolabe-mcp/server.py"],
      "env": {
        "ASTROLABE_CONFIG": "path/to/astrolabe-mcp/config.json"
      }
    }
  }
}
```

## Что НЕ входит в MVP

- Запись файлов через MCP (создание тасков, обновление рефов)
- Синхронизация рефов между проектами
- Семантический поиск (эмбеддинги)
- Composable instructions (сборка проектных инструкций из блоков)
- Валидация документов (соответствие шаблонам)
- File watcher (автообновление индекса)
- HTTP / CLI транспорты
- Детекция дубликатов (один реф скопирован в 3 проекта)

## Открытые вопросы

1. ~~Формат `doc_id` — `project::rel_path` достаточно?~~ **Решено:** да, `project::rel_path` — стабильный формат
2. Как обрабатывать ситуацию "файл создан, но reindex ещё не запущен"?
3. ~~Нужен ли лимит на размер файла при `read_doc()`?~~ **Решено:** `max_file_size_kb` в конфиге, при превышении — truncated + предложение использовать section/range

---

*Вдохновлено подходом "harness engineering" (OpenAI, 2025): документация для агентов, структурированная как система, а не как набор файлов.*
