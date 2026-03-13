# PLAN — Astrolabe Web UI v0.8.0

Feature description: `docs/WEB_UI.md`

- [x] **Step 0**: Feature description (`docs/WEB_UI.md`), spec (`docs/specs/spec_web.md` DRAFT), PLAN.md + PROGRESS.md
- [x] **Step 1**: Add `[web]` deps to pyproject.toml, install, vendor static assets (pico.css, htmx.js)
- [x] **Step 2**: `web/state.py` — AppState class with config loading, index merge, storage routing, reload
- [x] **Step 3**: `web/app.py` + `web/__main__.py` — FastAPI factory, lifespan, static mount, Jinja2 setup
- [x] **Step 4**: `base.html` + `app.css` — layout with nav, Pico CSS, HTMX
- [x] **Step 5**: Dashboard (`cosmos.html` + route) — stats bar, progress bar, project table, type badges. All elements clickable → `/cards?filter=...`
- [x] **Step 6**: Card list (`cards.html` + routes) — table, filters (project, type, stale/empty/desync), HTMX partial, pagination
- [x] **Step 7**: Card detail + inline edit (`card.html` + API routes) — view/edit toggle, save via update_card()
- [x] **Step 8**: Document reader (`doc.html` + route) — markdown rendering via mistune, section nav
- [x] **Step 9**: Search (`search.html` + routes) — live search with HTMX, results partial
- [x] **Step 10**: Reindex — three buttons: Update (immediate), Clean and Rebuild (with confirmation modal). Toast with results
- [x] **Step 11**: Tests — 24 tests: routes, state management, card editing flow
- [x] **Step 12**: Update ARCHITECTURE.md, spec_web.md status → READY, version → 0.8.0
