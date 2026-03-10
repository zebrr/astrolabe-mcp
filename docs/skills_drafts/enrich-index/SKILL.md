---
name: enrich-index
description: >-
  Batch-enrich astrolabe index cards. Use when the user asks to enrich, classify,
  or describe documents in the astrolabe index, or when list_docs(stale=true)
  shows unenriched cards. Reads each file, determines its type, writes a summary,
  keywords, and extracts headings, then calls update_index_tool.
context: fork
allowed-tools:
  - mcp__astrolabe__list_docs
  - mcp__astrolabe__read_doc
  - mcp__astrolabe__update_index_tool
  - mcp__astrolabe__get_cosmos
  - mcp__astrolabe__get_doc_types
---

# Enrich Astrolabe Index

Batch-enrich document cards in the astrolabe index. You read each file, understand it, classify it, and write metadata so that `search_docs` can find it later.

## Workflow

1. Call `get_doc_types()` to load the document type vocabulary (types, descriptions, examples)
2. Call `get_cosmos()` to see available projects and index health
3. Call `list_docs(stale=true)` to get cards that need enrichment (empty or content-changed).
   Response is an envelope: `{"total": N, "result": [...], "hint": "..."}`.
   Cards are in `response["result"]`. If `total` exceeds the page size, call again with `offset=` to get the next page. Collect all cards before starting enrichment.
4. For each card, in batches of 5-10:
   a. If the file has a binary extension (media or binary_doc) → assign the appropriate type, summary by filename, skip `read_doc()`
   b. Otherwise, call `read_doc(doc_id)` to read the file content
   c. Analyze the content and determine:
      - **type** — one of the types from `get_doc_types()` vocabulary
      - **summary** — 1-2 sentence description of what the file contains and why it matters (see Writing Good Summaries)
      - **keywords** — 5-15 keywords for search (see Writing Good Keywords)
      - **headings** — extract verbatim ATX markdown headings from the content (see Extracting Headings)
   d. Call `update_index_tool(doc_id, type=..., summary=..., keywords=[...], headings=[...])`
5. After finishing all cards, report: how many enriched, any errors

## Classification Rules

Use ONLY types from the `get_doc_types()` vocabulary. If a file does not fit any type — assign `undef`. Do NOT invent new types. The server validates types — unknown types will be rejected.

**Classify by content, not by filename.** A file named "референс" may be a design doc. A file named "plan" may be a task. Always read the file first, then decide.

**Skill vs reference:** A file is a `skill` only if it has a SKILL.md with YAML frontmatter. A methodology doc with "skill" in the name is NOT a skill — it's a `reference`.

## Writing Good Summaries

- 1-2 sentences, factual, no fluff
- Answer: "What is this file and what does it contain?"
- Include the most important detail (e.g., which API, which module, which workflow)
- Write in the document's language. Russian doc → Russian summary. English doc → English summary. Mixed-language → use the dominant language.

**Good (English doc):** "Pydantic models for astrolabe data structures: AppConfig, DocCard, IndexData, SearchResult, CosmosResponse. Defines the data contract between all modules."

**Good (Russian doc):** "Спецификация модуля индексации: сканирование файловой системы, построение индекса, детекция изменений по хешу, три режима переиндексации (update, clean, rebuild)."

**Bad:** "This file contains models." / "An important configuration file for the project."

## Writing Good Keywords

- 5-15 keywords, lowercase
- Include: main topic, technology/tool names, key concepts, proper nouns
- Exclude: generic words (file, document, code, project), stop words
- Think: "What would someone search for to find this file?"

**Bilingual keywords:** If a document is in Russian (or mixed), add keywords in both Russian and English for key concepts. This lets the document be found via either language.

**Good (Russian doc):** `["спецификация", "specification", "индексация", "indexing", "хеш", "hash", "переиндексация", "reindex", "детекция-изменений", "change-detection"]`

**Good (English doc):** `["pydantic", "models", "doccard", "appconfig", "indexdata", "data-contract"]`

**Temporal markers:** If a document has a clear date context (meeting notes, reports, changelogs, plans), add date keywords in multiple formats:
`["2025-11", "ноябрь 2025", "november 2025"]`

**Bad:** `["code", "python", "file", "important"]`

## Extracting Headings

Headings have weight 2.0 in search — passing them dramatically improves findability of structured documents.

- Extract ATX markdown headings verbatim (lines matching `^#{1,6}\s+(.+)$`)
- Keep original language and casing — do NOT translate
- Pass heading text only, without the `#` prefix
- For non-markdown files (`.py`, `.json`, `.yaml`, etc.) — omit headings
- For markdown files with no headings — omit headings (don't invent them)

**Example:** A file with `## Рабочий процесс`, `## Типы документов`, `### Бинарные файлы` →
`["Рабочий процесс", "Типы документов", "Бинарные файлы"]`

## Binary & Media Files

These files cannot be read as text. Do NOT call `read_doc()` — it will return `[binary file]`. Classify by filename and location.

**binary_doc** — files with extensions: .pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx

**media** — files with extensions: .jpg, .jpeg, .png, .gif, .svg, .webp, .mp3, .wav, .ogg, .flac, .mp4, .mov, .avi, .webm

For both types:
- Summary: describe what the file likely contains based on its name and parent directory
- Keywords: extract meaningful terms from the filename

## Batching

- Process 5-10 files per batch to stay within context limits
- After each batch, briefly report progress (e.g., "Enriched 8/23 cards")
- If a file is too large (truncated), classify based on what you can see + the filename
- If a file cannot be read (error), skip it and report at the end

## Important

- Do NOT re-enrich cards that already have type + summary + keywords unless the user explicitly asks
- `list_docs(stale=true)` returns only cards that need work — trust it
- After enrichment, the user can verify with `search_docs(query)` to test search quality
