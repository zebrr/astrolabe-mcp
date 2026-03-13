# Astrolabe Web UI — Описание фичи

> Версия: 0.8.0
> Статус: планирование
> Дата: 2026-03-14

## Проблема

Astrolabe-индекс управляется только через MCP-агента. Обогащение карточек полностью автоматическое — агент читает файл, классифицирует, пишет summary/keywords/headings. Но:

- **Агент иногда ошибается** — неправильный тип, плохое summary, лишние keywords. Исправить можно только через `update_index()` в CLI-сессии
- **Нет обзора индекса** — чтобы посмотреть состояние, нужно вызвать `get_cosmos()` через агента
- **Нет визуального просмотра документов** — `read_doc()` возвращает raw текст, markdown не рендерится
- **Нет удобного поиска** — `search_docs()` через агента, результаты в JSON
- **Переиндексация только через агента** — `reindex()` требует MCP-сессии

## Решение

Локальный веб-интерфейс к astrolabe — HTTP-сервер, который работает параллельно с MCP-сервером и использует тот же индекс. Браузерный UI для просмотра, поиска и **ручного редактирования карточек**.

Запуск: `.venv/bin/python -m astrolabe.web` → http://localhost:8420

## Сценарии использования

### Сценарий 1: Обзор состояния индекса
```
Пользователь → открывает http://localhost:8420
Видит → дашборд: stats bar, таблицу проектов с coverage, типы документов
Действие → кликает на проект, тип, stale или empty → переход к отфильтрованному
           списку карточек (постраничный вывод)
```

### Сценарий 2: Просмотр карточек проекта
```
Пользователь → переходит в Cards, выбирает фильтр project=web-app
Видит → таблицу карточек: имя файла, тип (бейдж), summary (truncated), статус
        stale-карточки подсвечены жёлтым, empty — серым
Действие → кликает на карточку для детального просмотра
```

### Сценарий 3: Исправление ошибки агента (главный сценарий)
```
Пользователь → открывает карточку "API Reference.md"
Видит → type: "document" (неправильно!), summary неточный
Действие → жмёт [Edit]
        → меняет type на "reference" из dropdown
        → правит summary в textarea
        → добавляет пропущенные keywords
        → жмёт [Save]
Результат → карточка обновлена, enriched_at обновлён
           MCP-агент при следующем get_card() видит исправления
```

### Сценарий 4: Чтение документа с форматированием
```
Пользователь → из карточки жмёт [Read doc]
Видит → содержимое файла с markdown-рендерингом:
        заголовки, списки, код с подсветкой, таблицы
        сайдбар с навигацией по секциям (из headings)
Действие → кликает на секцию в сайдбаре → скролл к секции
```

### Сценарий 5: Поиск по индексу
```
Пользователь → вводит "api migration" в поисковую строку
Видит → результаты по мере ввода (live search, задержка 300ms)
        карточки отсортированы по relevance, с проектом и типом
Действие → кликает на результат → переходит к карточке
```

### Сценарий 6: Переиндексация
```
Пользователь → на дашборде видит три кнопки реиндекса:
  [Update] — срабатывает сразу
  [Clean]  — модалка подтверждения → выполнение
  [Rebuild] — модалка подтверждения → выполнение
Результат → toast с результатами: scanned 52, new 2, stale 4...
            дашборд обновляется
```

### Сценарий 7: Синхронизация с MCP
```
Агент через MCP обогатил 5 карточек
Пользователь → в веб-UI жмёт [Refresh]
Результат → индекс перезагружен из storage, видит свежие данные
```

## Функции интерфейса

| Функция | Описание | Приоритет |
|---------|----------|-----------|
| **Dashboard** | Обзор: stats bar, progress bar, проекты, типы | Must |
| **Card list** | Таблица карточек с фильтрами (project, type, stale/empty/desync), пагинация | Must |
| **Card detail** | Просмотр карточки: метаданные + обогащённые поля + статус | Must |
| **Card edit** | Inline-редактирование: type (dropdown), summary (textarea), keywords (tags), headings (list) | Must — главная фича |
| **Doc reader** | Просмотр документа с markdown-рендерингом, навигация по секциям | Must |
| **Search** | Live-поиск с фильтрами project/type, результаты с relevance | Must |
| **Reindex** | Кнопка переиндексации с выбором режима, toast с результатами | Should |
| **Refresh** | Перезагрузка индекса из storage (подхватить изменения от MCP) | Should |

## Технические решения

- **Стек**: FastAPI + Jinja2 + HTMX (Python only, без Node.js)
- **Процесс**: отдельный от MCP-сервера, общий storage. Запуск через `.venv` как и MCP
- **CSS**: Pico CSS (classless, vendored)
- **Markdown**: mistune (server-side rendering)
- **Зависимости**: опциональная группа `[web]` в pyproject.toml
- **UI**: английский, compact layout

## Структура файлов

Всё внутри пакета `src/astrolabe/web/` — шаблоны, статика, код. Устанавливается через `pip install -e ".[web]"`, пути через `pathlib(__file__)`.

```
src/astrolabe/web/
├── __init__.py
├── __main__.py              # entry point: python -m astrolabe.web
├── app.py                   # FastAPI factory, lifespan, static/templates setup
├── state.py                 # AppState: config, index, storage management
├── routes_pages.py          # HTML page routes (full renders)
├── routes_api.py            # HTMX API routes (HTML fragments)
├── templates/               # Jinja2 шаблоны
│   ├── base.html            # Layout: nav, Pico CSS, HTMX
│   ├── cosmos.html          # Dashboard
│   ├── cards.html           # Card list + filters
│   ├── card.html            # Card detail + inline edit
│   ├── doc.html             # Document viewer (markdown)
│   ├── search.html          # Search page
│   └── partials/            # HTMX-фрагменты для partial swap
│       ├── card_list.html
│       ├── card_fields.html
│       ├── search_results.html
│       └── toast.html
└── static/                  # CSS, JS (vendored, без CDN)
    ├── pico.min.css          # ~10KB
    ├── htmx.min.js           # ~14KB
    └── app.css               # Кастомные стили (badges, tags, progress bar)
```

## Что НЕ входит

- Авторизация — localhost only, один пользователь
- Редактирование содержимого файлов — только карточки индекса
- Batch-операции — массовое обогащение остаётся за агентом
- Real-time обновления — явная кнопка Refresh
- Мобильная версия — десктопный браузер
