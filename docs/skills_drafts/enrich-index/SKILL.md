---
name: enrich-index
description: >-
  Batch-enrich astrolabe index cards. Use when the user asks to enrich, classify,
  or describe documents in the astrolabe index, or when list_docs(stale=true)
  shows unenriched cards. Reads each file, determines its type, writes a summary
  and keywords, then calls update_index_tool.
context: fork
allowed-tools:
  - mcp__astrolabe__list_docs
  - mcp__astrolabe__get_doc
  - mcp__astrolabe__update_index_tool
  - mcp__astrolabe__get_cosmos
---

# Enrich Astrolabe Index

Batch-enrich document cards in the astrolabe index. You read each file, understand it, classify it, and write metadata so that `search_docs` can find it later.

## Workflow

1. Call `get_cosmos()` to see available projects and document types
2. Call `list_docs(stale=true)` to get all cards that need enrichment (empty or content-changed)
3. For each card, in batches of 5-10:
   a. If the file has a binary extension (media or binary_doc) → assign the appropriate type, summary by filename, skip `get_doc()`
   b. Otherwise, call `get_doc(doc_id)` to read the file content
   c. Analyze the content and determine:
      - **type** — one of the document types from `get_cosmos().document_types`
      - **summary** — 1-2 sentence description of what the file contains and why it matters
      - **keywords** — 3-8 keywords for search (lowercase, specific terms that someone would search for)
   c. Call `update_index_tool(doc_id, type=..., summary=..., keywords=[...])`
4. After finishing all cards, report: how many enriched, any errors

## Document Types

Use ONLY these types. If a file does not fit any type — assign `undef`. Do NOT invent new types.

**Classify by content, not by filename.** A file named "референс" may be a design doc. A file named "plan" may be a task. Always read the file first, then decide.

- **instruction** — project rules, agent constraints (CLAUDE.md, PROJECT.md)
- **reference** — API/tool/methodology reference material
- **task** — work assignment with steps and acceptance criteria
- **report** — task completion report
- **spec** — technical specification, read instead of code
- **document** — concept, architecture, design doc, README
- **skill** — agent skill with SKILL.md (YAML frontmatter required). A methodology doc with "skill" in the name is NOT a skill — it's a reference
- **utility** — reusable script or tool
- **project_state** — plan, progress, changelog, todo
- **binary_doc** — PDF, Word, Excel, PowerPoint (see Binary & Media Files section below)
- **media** — image, audio, video (see Binary & Media Files section below)
- **undef** — catch-all for files that don't fit any other type. Always explain in summary what the file contains

## Writing Good Summaries

- 1-2 sentences, factual, no fluff
- Answer: "What is this file and what does it contain?"
- Include the most important detail (e.g., which API, which module, which workflow)
- Write in English

**Good:** "Pydantic models for astrolabe data structures: AppConfig, DocCard, IndexData, SearchResult, CosmosResponse. Defines the data contract between all modules."

**Bad:** "This file contains models." / "An important configuration file for the project."

## Writing Good Keywords

- 3-8 keywords, lowercase
- Include: main topic, technology/tool names, key concepts
- Exclude: generic words (file, document, code, project), stop words
- Think: "What would someone search for to find this file?"

**Good:** `["pydantic", "models", "doccard", "appconfig", "indexdata", "data-contract"]`

**Bad:** `["code", "python", "file", "important"]`

## Binary & Media Files

These files cannot be read as text. Do NOT call `get_doc()` — it will return `[binary file]`. Classify by filename and location.

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
