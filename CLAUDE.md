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

## Quality Checks (before every step completion)

```bash
source .venv/bin/activate
ruff check src/ tests/
ruff format src/ tests/
mypy src/
python -m pytest -v
```

## Artifacts

| File | Purpose | Changed by |
|------|---------|-----------|
| `CLAUDE.md` | Mechanics: rules, commands, conventions | Together with user |
| `docs/ARCHITECTURE.md` | Navigation: structure, modules, key context (keep short) | Agent, after each step |
| `docs/PLAN.md` | Current milestone work plan | Agent |
| `docs/PROGRESS.md` | What was done, decisions, notes | Agent |
| `docs/CONCEPT.md` | Requirements source of truth | Read-only |
| `docs/specs/*.md` | Module specs (read INSTEAD of code) | Agent |
| `docs/archive/` | Archived PLAN.md + PROGRESS.md from past milestones | Agent |
| `runtime/` | Config, doc_types, index (not committed except examples) | User + server |

### Spec Statuses (strictly three values)

- `DRAFT` — spec written, code not yet implemented (spec is written BEFORE code)
- `IN_PROGRESS` — spec updated for new requirements, code being aligned (spec first, then code)
- `READY` — spec stable, code matches spec, no work in progress

## Session Start

Check if `docs/PLAN.md` exists:

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
- Do NOT auto-create plans without user input

## Work Rhythm

After completing each plan step:

1. Quality checks (ruff + mypy + pytest)
2. Update spec status → `READY`
3. Mark step done in `docs/PLAN.md` (check the box)
4. Review all remaining steps — still relevant? Need update/split/remove?
5. Append event to `docs/PROGRESS.md` (with real timestamp)
6. Update `docs/ARCHITECTURE.md` if structure changed
7. If review required → set STATUS: `WAITING_REVIEW`, show result to user

## PLAN.md Rules

**Format:** flat numbered list with checkboxes. Each step has: Input, Action, Output, Checkpoint, Review.

**Execution:**
- Execute steps sequentially, top to bottom
- Check the box when done — NEVER edit or delete completed steps
- After each step, review remaining steps: still relevant? Need update?

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
- Archive: docs/PLAN.md + docs/PROGRESS.md → `docs/archive/<milestone>/`
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

## Communication

- Language: Russian (discussion, user-docs), English (code, specs, docstrings, comments)
- When uncertain: **ASK**, don't assume
- Commits: only on user request
