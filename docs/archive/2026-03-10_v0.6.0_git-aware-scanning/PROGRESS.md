# Progress: Git-aware scanning — astrolabe-mcp 0.6.0

## STATUS: COMPLETED

## Current State

All steps complete. v0.6.0 ready.

## Decisions

- Git ls-files as primary file source, rglob as fallback for non-git dirs
- Two new helpers: `_list_files_git()`, `_list_files_rglob()`
- Config cleanup: remove gitignore-redundant entries, keep domain-specific only
- Existing tests unaffected (fake_project is not a git repo → tests rglob fallback)

---

## Progress Events

### E001 — 2026-03-10 00:17 — Step 0: Archive + init
- Archived v0.5.2 docs to `docs/archive/2026-03-10_v0.5.2_desync-visibility/`
- Created new PLAN.md + PROGRESS.md for v0.6.0

### E002 — 2026-03-10 00:17 — Step 1: Spec update
- Updated spec_index.md: scan_project() now documents git-aware + rglob fallback
- Added `_list_files_git()`, `_list_files_rglob()` to Internal Functions
- Added `subprocess` to dependencies
- Status: IN_PROGRESS

### E003 — 2026-03-10 00:18 — Step 2: Implement git-aware scanning
- Added `import subprocess` to index.py
- New `_list_files_git()`: git ls-files with timeout, FileNotFoundError/returncode fallback
- New `_list_files_rglob()`: extracted existing rglob logic
- Refactored `scan_project()`: two-tier discovery, uniform filtering chain

### E004 — 2026-03-10 00:18 — Step 3: Config cleanup
- Removed gitignore-redundant entries from config.example.json ignore_dirs and ignore_files
- Kept domain-specific: ignore_dirs=["src","lib","app","tests","test"], ignore_files=["*.lock"]
- Added `_ignore_note` explaining the distinction

### E005 — 2026-03-10 00:20 — Step 4: Tests
- New fixtures: `fake_git_project`, `git_config`, `_git` helper in conftest.py
- New test classes: `TestGitAwareScan` (7 tests), `TestListFilesGit` (5 tests), `TestListFilesRglob` (2 tests)
- Existing tests unchanged — use rglob fallback path

### E006 — 2026-03-10 00:20 — Step 5: Quality checks
- ruff check: passed
- ruff format: 1 file reformatted (test_index.py)
- mypy: success, no issues
- pytest: 214 passed (was 200, +14 new git-aware tests)

### E007 — 2026-03-10 00:21 — Step 6: Spec finalized
- spec_index.md status: READY

### E008 — 2026-03-10 00:21 — Step 7: Docs update
- ARCHITECTURE.md: added git-aware scanning to Key Technical Decisions, updated index.py description
- README.md: added git-aware scanning to Key Features, cleaned config example, updated description
- CONCEPT.md: updated config example and ignore description

### E009 — 2026-03-10 00:22 — Step 8: Version bump
- pyproject.toml: 0.5.2 → 0.6.0

### E010 — 2026-03-10 00:22 — Step 9: Final checks + close
- ruff check: passed
- ruff format: all formatted
- mypy: success
- pytest: 214 passed (14 new git-aware tests)
- Plan complete, STATUS → COMPLETED
