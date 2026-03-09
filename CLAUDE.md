# CLAUDE.md — astrolabe-mcp

MCP server for navigating the constellation of knowledge scattered across projects.

> «Ночь тиха; пустыня внемлет Богу, и звезда со звездою говорит» — Лермонтов. That's what we're building: projects talking to projects, agents talking to agents.

## Environment

- **Python 3.11+**, always work in venv
- **Cross-platform**: Windows and Mac, use `pathlib`
- macOS: `source .venv/bin/activate`
- Windows: `.venv\Scripts\activate`
- If `.venv` does not exist — create: `python3 -m venv .venv`

## Coding Standards

- PEP 8, type hints for all functions, docstrings in English
- Imports: stdlib → third-party → local, absolute imports
- `pytest` for tests, `tmp_path` fixtures (no real project paths)

## Communication

- Language: Russian (discussion, user-docs), English (code, specs, docstrings, comments)
- When uncertain: **ASK**, don't assume
- Commits: only on user request

## Artifacts

| File | Purpose | Changed by |
|------|---------|-----------|
| `CLAUDE.md` | Mechanics: rules, commands, conventions | Together with user |
| `docs/CONCEPT.md` | Requirements source of truth | Read-only (update with user approval on scope changes) |
| `docs/ARCHITECTURE.md` | Navigation: structure, modules, key context (keep short) | Agent, after each step |
| `docs/PLAN.md` | Current milestone work plan | Agent |
| `docs/PROGRESS.md` | What was done, decisions, notes | Agent |
| `docs/specs/*.md` | Module specs (read INSTEAD of code) | Agent |
| `docs/archive/` | Archived PLAN.md + PROGRESS.md from past milestones | Agent |
| `pyproject.toml` | Package metadata, version (semver) | Agent |
| `runtime/` | Config, doc_types, index (not committed except examples) | User + server |
| `.claude/skills/` | Active agent skills | Agent |
| `docs/skills_drafts/` | Draft skills before activation | Agent |

## Session Start

**Astrolabe index check** (if astrolabe MCP is connected):
- Call `get_cosmos()` → check `desync_documents`, `stale_documents`, `empty_documents`
- If `desync_documents > 0` — warn user: "N files out of sync, may need git pull in projects X, Y"
- If many stale/empty cards — suggest running `enrich-index` skill to update index coverage

**Development state** — check if `docs/PLAN.md` exists:

**docs/PLAN.md exists → check state:**

1. Read `docs/PROGRESS.md` → current STATUS
2. Read `docs/PLAN.md` → find unchecked steps

- **Has unchecked steps** → resume work:
  1. Read `docs/ARCHITECTURE.md` → project structure
  2. Read spec of current module → context
  3. Continue from next unchecked step

- **All steps checked (plan complete)** → ask user:
  - "Plan is complete. Archive to `docs/archive/` and start new milestone? Or add more steps?"
  - Do NOT auto-archive or auto-create new plans

- **STATUS is `WAITING_REVIEW`** → remind user:
  - "Waiting for your review of [step N]. See docs/PROGRESS.md for details."

- **STATUS is `BLOCKED`** → show blocker:
  - Read Decisions section, show what's blocking, ask user for guidance

**docs/PLAN.md does not exist → ask user:**

- "No active plan. What would you like to do?"
  - Create a new milestone plan (design phases, write PLAN.md)
  - Ad-hoc task (work without a plan, just execute what's asked)
  - Server/index work (enrichment, reindex, skills — see Astrolabe MCP Usage)
- Do NOT auto-create plans without user input

## Work Modes

Three modes of working, explicitly:

1. **Planned work** — feature, refactor, milestone. Full Code Change Pipeline with all steps.
   - **Before any code:** create PLAN.md + PROGRESS.md (Step 0). These are project artifacts for traceability across versions and decisions, NOT internal agent notes. The agent's internal reasoning is never a substitute.
   - PLAN.md must have all steps written before implementation begins.
   - PROGRESS.md must track decisions and events throughout the work.
   - User explicitly initiates planned work (e.g. "планируем", "новая задача", "milestone").
2. **Ad-hoc task** — user explicitly says "ad-hoc" or similar. No PLAN.md/PROGRESS.md, but same Code Change Pipeline for any code/config/spec changes. Steps marked `[Planned]` are skipped.
3. **Server/index work** — enrichment, reindex, skills usage. No code changes, no pipeline. Follow Astrolabe MCP Usage rules.

## Code Change Pipeline

Applies to **any** work that touches code, configs, or specs — both planned and ad-hoc.

**Before work:**
1. `[Planned]` Step must be written in PLAN.md before any code changes (follow PLAN.md Rules)
2. If spec exists or is needed → update spec FIRST (status: `DRAFT` or `IN_PROGRESS`)

**Work:**
3. Write/modify code
4. Quality checks (see commands below)

**After work:**
5. Update spec status → `READY` (if spec was changed)
6. Bump version in `pyproject.toml` (if significant change, semver)
7. Update docs if affected: `ARCHITECTURE.md`, `README.md`
8. If step creates/modifies a skill → update both `docs/skills_drafts/` and `.claude/skills/`
9. `[Planned]` Mark step done in PLAN.md, review remaining steps — still relevant? Need update/split/remove? (follow PLAN.md Rules)
10. `[Planned]` Append event to PROGRESS.md (with real timestamp via `date "+%Y-%m-%d %H:%M"`) (follow PROGRESS.md Rules)

## Quality Checks

```bash
source .venv/bin/activate
ruff check src/ tests/
ruff format src/ tests/
mypy src/
python -m pytest -v
```

## Spec Rules

Specs live in `docs/specs/*.md`. Read specs INSTEAD of code for module context.

**Statuses (strictly three values):**
- `DRAFT` — spec written, code not yet implemented (spec is written BEFORE code)
- `IN_PROGRESS` — spec updated for new requirements, code being aligned (spec first, then code)
- `READY` — spec stable, code matches spec, no work in progress

**Spec-first rule:** always update the spec BEFORE changing code. Never code first and document later.

## PLAN.md Rules

**Format:** flat numbered list with checkboxes. Each step has: Input, Action, Output, Checkpoint, Review.

**Execution:**
- Execute steps sequentially, top to bottom
- Check the box when done — NEVER edit or delete completed steps

**Modifying future steps:**
- **Update:** change description of a future step in place
- **Split:** replace with sub-steps using letter suffixes (5a, 5b, 5c)
- **Remove:** delete if no longer needed
- **Add:** append new steps at the end
- **NEVER** insert steps between completed steps

**Logging changes:**
- Every modification → add "Updated: YYYY-MM-DD — [reason]" line
- Note what changed in PROGRESS.md event

**Milestone completion:**
- All steps checked, final quality checks pass
- Archive: docs/PLAN.md + docs/PROGRESS.md → `docs/archive/YYYY-MM-DD_<version>_<milestone>/`
- New milestone → new docs/PLAN.md (or none if working ad hoc)

## PROGRESS.md Rules

**Two zones separated by `---`:**

- **Above `---`** (Status, Current State, Decisions) — update in place, never duplicate headers
- **Below `---`** (Progress Events) — append only, sequential numbering E001, E002...

**STATUS values (strictly four):** `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `WAITING_REVIEW`

**Timestamps:** always real system time via `date "+%Y-%m-%d %H:%M"`. Never estimate or invent.

**Decisions section:** key decisions with reasoning, updated in place. These survive context compression and inform future steps.

**Events:** created when a step starts, completes, plan changes, or a problem is encountered.

## ARCHITECTURE.md Rules

- Update after any step that changes project structure, modules, or dependencies
- Keep short — navigation aid, not documentation
- Contains: project structure tree, modules table (name / status / spec / purpose), dependency graph, MCP tools list, key technical decisions
- Do NOT write specs or detailed design here — that belongs in `docs/specs/`
- Module status in table tracks implementation state, not spec status

## CLAUDE.md Rules

- **NEVER** change without user approval
- After completing each plan step, analyze: is there something in CLAUDE.md that should be improved, added, or clarified?
- If yes → propose the change to the user (show the diff), wait for approval
- If no → move on silently
- This creates a self-improvement loop: the rules evolve as we learn what works

## Astrolabe MCP Usage

Rules for working with astrolabe MCP tools. This section is universal — copy to any project connected to astrolabe.

### Reindex

- After adding/removing/renaming files → call `reindex_tool()`
- After deleting/moving files → `reindex_tool(mode="clean")` removes desync cards, keeps enrichment
- After mass changes or broken index → `reindex_tool(mode="rebuild")` resets enrichment
- Cards from foreign projects (not in local config) are always preserved (pass-through)

### Enrichment

- **NEVER** enrich cards manually — use `enrich-index` skill as the source of enrichment rules
- Manual `update_index_tool()` only for single-field corrections (e.g., fixing a wrong type)
- **≤20 stale cards** — invoke the `enrich-index` skill directly (single thread)
- **>20 stale cards** — parallel enrichment:
  1. Read `.claude/skills/enrich-index/SKILL.md` for enrichment instructions
  2. Call `list_docs(stale=true)` to get all cards needing work
  3. Split cards into groups (by project, or by batches if one project is large)
  4. Launch subagents in parallel, each receiving: enrichment instructions from the skill + their assigned scope (project filter or list of doc_ids)

### Search & Navigation

- `get_cosmos()` — session overview, index health
- `search_docs(query)` — cross-project knowledge search
- `list_docs(project?, type?, stale?)` — browse by category
- `get_card(doc_id)` — inspect card metadata (type, summary, keywords)
- `read_doc(doc_id, section?)` — targeted reading by heading

### Desync

- `desync_documents > 0` → files missing locally or enrichment from another machine
- Warn user, suggest `git pull` for affected projects
- To clean up genuinely deleted files → `reindex_tool(mode="clean")`
