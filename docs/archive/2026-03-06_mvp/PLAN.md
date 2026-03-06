# Plan — Astrolabe MCP MVP

Created: 2026-03-06

## Steps

- [x] 1. Setup project environment
  Input: concept doc, input/ examples, current CLAUDE.md
  Action: venv, pyproject.toml, config.example.json, doc_types.yaml, CLAUDE.md, ARCHITECTURE.md, delete input/
  Output: working dev environment, all root artifacts
  Checkpoint: venv works, pip install succeeds, ruff/mypy/pytest runnable
  Review: YES — user reviews CLAUDE.md

- [x] 2. Data models
  Input: docs/CONCEPT.md (data formats)
  Action: write spec_models.md (DRAFT), implement models.py, write tests
  Output: spec (READY), models.py, test_models.py — all green
  Checkpoint: ruff ✓ mypy ✓ pytest ✓, models match concept doc formats
  Review: YES — models define data contracts

- [x] 3. Config loading
  Input: models.py + spec
  Action: write spec_config.md (DRAFT), implement config.py, write tests
  Output: spec (READY), config.py, test_config.py
  Checkpoint: ruff ✓ mypy ✓ pytest ✓, loads config.example.json correctly
  Review: NO

- [x] 4. Index (core)
  Input: models + config + specs
  Action: write spec_index.md (DRAFT), implement index.py, conftest.py fixtures, write tests
  Output: spec (READY), index.py, test_index.py, conftest.py
  Checkpoint: ruff ✓ mypy ✓ pytest ✓, scan/hash/stale/update/reindex all tested
  Review: YES — core system module

- [x] 5. Reader + Search
  Input: models + spec
  Action: write spec_reader.md + spec_search.md (DRAFT), implement reader.py + search.py, write tests
  Output: specs (READY), reader.py, search.py, tests
  Checkpoint: ruff ✓ mypy ✓ pytest ✓, section extraction + weighted search tested
  Review: NO

- [x] 6. MCP Server
  Input: all core modules + specs
  Action: write spec_server.md (DRAFT), implement server.py with 7 MCP tools, write tests
  Output: spec (READY), server.py, test_server.py
  Checkpoint: ruff ✓ mypy ✓ pytest ✓, all 7 tools respond correctly
  Review: YES — agent interface contract

- [x] 7. Integration + Polish
  Input: everything
  Action: end-to-end test, README.md, final quality checks, archive plan
  Output: working server, README, PLAN+PROGRESS archived to docs/archive/mvp/
  Checkpoint: e2e test passes, server starts, tools respond
  Review: YES — user live-tests with Claude Code

- [x] 8. Real doc_types
  Input: user's actual project documentation patterns
  Action: user defines real doc_types.yaml with production types and descriptions
  Output: runtime/doc_types.yaml with real types
  Checkpoint: get_cosmos() shows correct type descriptions
  Review: YES — user validates types

- [x] 9. Enrichment skill
  Input: Anthropic skill refs (docs/), current tool API, real doc_types
  Action: write Claude Code skill for batch enrichment via update_index_tool
  Output: skill file, tested on real index
  Checkpoint: skill enriches cards correctly, index persists
  Review: YES — user tests skill live

- [x] 9a. Hard typing + media support
  Input: doc_types.yaml, skill, concept, reader.py
  Action: add media/undef types, fix binary reader, update concept for MVP
  Output: updated types, reader handles binaries, skill uses hard types
  Checkpoint: ruff ✓ mypy ✓ pytest ✓
  Review: NO

- [x] 10. Live enrichment test
  Input: real projects in config, real doc_types, enrichment skill
  Action: run enrichment on real files, verify search quality
  Output: enriched index, search results validation
  Checkpoint: search_docs returns relevant results for real queries
  Review: YES — user validates quality

- [x] 11. Open-source README + sanitize CONCEPT.md
  Input: current Russian README, concept.md with personal project names
  Action: rewrite README in English, rename concept.md → CONCEPT.md, sanitize personal names
  Output: English README with badges/features/quickstart/tools/limitations, sanitized CONCEPT.md
  Checkpoint: no Russian in README, no personal names in README or CONCEPT.md
  Review: YES — user validates before commit

Updated: 2026-03-06 — added steps 8-11

## Notes

Steps 1-7: MVP server (complete).
Steps 8-10: enrichment and real-world testing.
