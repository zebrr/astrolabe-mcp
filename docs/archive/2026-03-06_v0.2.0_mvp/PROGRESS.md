# Progress

## Status

STATUS: COMPLETED

## Current State

Step: 11 — Open-source README (done).
Quality: ruff ✓ mypy ✓ pytest ✓ (99 passed)

## Decisions

- Specs use strict statuses: DRAFT → IN_PROGRESS → READY. Spec-first: update spec, then align code.
- ignore_dirs fully configurable (no hardcoded defaults in code).
- filelock for concurrent .doc-index.json access.
- No formal task-report files — PLAN.md steps serve as tasks, PROGRESS.md events as reports.
- PLAN.md + PROGRESS.md archived to docs/archive/<milestone>/ on milestone completion.

---

## Progress Events

### E001 (2026-03-06 15:03)
Step 1 started. Setting up project environment: venv, pyproject.toml, directory structure, config files, root artifacts.

### E002 (2026-03-06 15:07)
Step 1 nearly complete. Created: venv (Python 3.14), pyproject.toml (setuptools, not hatchling — 3.14 compat), config.example.json, doc_types.yaml, CLAUDE.md, ARCHITECTURE.md, PLAN.md, PROGRESS.md. Renamed concept doc → docs/concept.md. Deleted input/. Created docs/specs/, docs/archive/, src/astrolabe/, tests/. Quality: ruff ✓ mypy ✓. Waiting user review of CLAUDE.md.

### E003 (2026-03-06 17:21)
Step 1 complete. Added ARCHITECTURE.md Rules and CLAUDE.md Rules sections to CLAUDE.md. Also fixed Communication section (added "user-docs" to Russian scope). Quality: ruff ✓ mypy ✓. Waiting user review of final CLAUDE.md before proceeding to Step 2 (Models).

### E004 (2026-03-06 17:24)
Step 2 complete. Created spec_models.md (DRAFT→READY), models.py (7 models: AppConfig, DocCard, IndexData, ProjectSummary, TypeSummary, CosmosResponse, SearchResult), test_models.py (16 tests). Installed package in editable mode (`pip install -e ".[dev]"`). Quality: ruff ✓ mypy ✓ pytest ✓ (16 passed). DocCard has computed properties: doc_id, is_stale, is_empty.

### E005 (2026-03-06 17:27)
Step 3 complete. Created spec_config.md (DRAFT→READY), config.py (load_config, load_doc_types), test_config.py (12 tests). load_config resolves index_path relative to config dir, keeps non-existent project paths. load_doc_types returns {} if file missing. Quality: ruff ✓ mypy ✓ pytest ✓ (28 passed).

### E006 (2026-03-06 17:30)
Step 4 complete. Created spec_index.md (DRAFT→READY), index.py (scan_project, load_index, save_index, build_index, reindex, update_card, ReindexStats), conftest.py (fake_project + sample_config fixtures), test_index.py (24 tests). Key features: filelock for concurrent access, atomic save via tempfile+rename, corrupt index backup, MD5 content hashing, enrichment preservation on reindex. Quality: ruff ✓ mypy ✓ pytest ✓ (52 passed). Waiting user review — core module.

### E007 (2026-03-06 17:37)
Step 5 complete. Created spec_reader.md + spec_search.md (DRAFT→READY), reader.py (read_file, extract_headings, ReadResult), search.py (search with field weights), test_reader.py (14 tests), test_search.py (12 tests). Reader: ATX section extraction, line range, truncation. Search: token matching, weights (keywords 3.0, filename 2.5, headings 2.0, summary 1.0), exact match bonus. Quality: ruff ✓ mypy ✓ pytest ✓ (78 passed).

### E008 (2026-03-06 17:40)
Step 6 complete. Created spec_server.md (DRAFT→READY), server.py (7 MCP tools: get_cosmos, list_docs, search_docs, read_doc, get_doc, update_index_tool, reindex_tool), test_server.py (20 tests). Startup: config from ASTROLABE_CONFIG env var, auto-reindex, doc_types loading. All tools return structured dicts, errors include hints. Quality: ruff ✓ mypy ✓ pytest ✓ (98 passed).

### E009 (2026-03-06 17:42)
Step 7 complete. Live smoke test passed: server starts, indexes 17 docs from astrolabe-mcp itself, search/read/section extraction work. Created README.md, __main__.py (python -m astrolabe entry point). All 7 steps done. MVP ready for live testing with Claude Code.

### E010 (2026-03-06 21:15)
Project reorganization: moved runtime files (config, doc_types, index) to runtime/, moved ARCHITECTURE/PLAN/PROGRESS to docs/. Updated all references in CLAUDE.md, README, ARCHITECTURE, server.py, .mcp.json. Added steps 8-10 to plan. Cleaned up root egg-info.

### E011 (2026-03-06 22:09)
Step 8 complete. User defined real doc_types.yaml with 9 types: instruction, reference, task, report, spec, document, skill, utility, project_state. Key decision: renamed project_doc → project_state (operational status docs), moved README into document type.

### E012 (2026-03-06 22:15)
Step 9 complete. Created enrichment skill in docs/skills_drafts/enrich-index/SKILL.md. Skill uses YAML frontmatter (name, description, allowed-tools, context: fork), follows progressive disclosure pattern. Workflow: get_cosmos → list_docs(stale=true) → get_doc per card → update_index_tool with type/summary/keywords. Also moved skills_drafts/ from root to docs/skills_drafts/ per user request.

### E013 (2026-03-06 22:55)
Step 9a complete. Switched from soft to hard typing for MVP. Added 2 types: media (images/audio/video, classified by extension) and undef (catch-all). Added media extensions to index_extensions in config. Fixed reader.py to handle binary files (UnicodeDecodeError → ReadResult with "[binary file]"). Updated skill for hard typing (ONLY listed types, undef for unknown, media section). Updated concept.md: "мягкая типизация" → "управляемая типизация". Quality: ruff ✓ mypy ✓ pytest ✓ (99 passed, +1 binary file test).

### E014 (2026-03-06 23:26)
Step 10 complete. Live enrichment test on 40 docs (astrolabe-mcp project + tempo_docs test set with mixed types including 3 PNG media files). Forked agent enriched all 40 in 4 batches. Distribution: reference 12, document 6, spec 6, project_state 4, instruction 3, media 3, report 2, skill 2, task 2. Two misclassifications found (agent biased by filename): K2-18 "референс" → fixed to document, Multi-Agent "AI-skill" → fixed to reference. Skill updated with two rules: "classify by content not filename" and "skill = SKILL.md with YAML frontmatter". Also added binary_doc type for PDF/Office files. MVP milestone complete.

### E015 (2026-03-06 23:40)
Step 11 complete. Rewrote README in English for open-source: badges (Python 3.11+, MCP, MIT), features, quick start, config, client connection (CC + Desktop), enrichment example session, MCP tools table, limitations, contributing. Renamed concept.md → CONCEPT.md, sanitized all personal project names (neyra→web-app, k2-18→data-lib, etc.). Updated references in CLAUDE.md, ARCHITECTURE.md, PLAN.md.
