"""HTML page routes for the web UI."""

from typing import Any
from urllib.parse import quote

import mistune
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrolabe.index import build_hash_map
from astrolabe.web.app import get_state

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def cosmos_page(request: Request) -> Any:
    """Dashboard page."""
    state = get_state(request)
    cosmos = state.get_cosmos()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "cosmos.html",
        {"request": request, "cosmos": cosmos, "quote": quote},
    )


@router.get("/cards", response_class=HTMLResponse)
async def cards_page(
    request: Request,
    project: str | None = None,
    type: str | None = None,
    stale: bool = False,
    empty: bool = False,
    desync: bool = False,
    diverged: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Card list page with filters."""
    state = get_state(request)
    # Normalize empty strings from form selects to None
    project = project or None
    type = type or None
    cards, total = state.list_cards(
        project=project,
        type=type,
        stale=stale,
        empty=empty,
        desync=desync,
        diverged=diverged,
        limit=limit,
        offset=offset,
    )

    projects = sorted({c.project for c in state.index.documents.values()})
    types = sorted({c.type for c in state.index.documents.values() if c.type})
    hash_map = build_hash_map(state.index.documents)

    # Counts for filter checkboxes — scoped to current project/type filters
    count_stale = 0
    count_empty = 0
    count_desync = 0
    count_diverged = 0
    for c in state.index.documents.values():
        if project is not None and c.project != project:
            continue
        if type is not None and c.type != type:
            continue
        if c.is_stale:
            count_stale += 1
        if c.is_empty:
            count_empty += 1
        if state.is_desync(c):
            count_desync += 1
        if c.diverged_from:
            count_diverged += 1

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "cards.html",
        {
            "request": request,
            "cards": cards,
            "total": total,
            "projects": projects,
            "types": types,
            "filter_project": project,
            "filter_type": type,
            "filter_stale": stale,
            "filter_empty": empty,
            "filter_desync": desync,
            "filter_diverged": diverged,
            "count_stale": count_stale,
            "count_empty": count_empty,
            "count_desync": count_desync,
            "count_diverged": count_diverged,
            "limit": limit,
            "offset": offset,
            "quote": quote,
            "state": state,
            "hash_map": hash_map,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str | None = None) -> Any:
    """Search page. Accepts optional q= param from nav search form."""
    state = get_state(request)
    query = q.strip() if q else ""
    results = state.search_cards(query) if query else []
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "search.html",
        {"request": request, "query": query, "results": results, "quote": quote},
    )


@router.get("/cards/{doc_id:path}", response_class=HTMLResponse)
async def card_page(request: Request, doc_id: str) -> Any:
    """Card detail page."""
    state = get_state(request)
    card = state.index.documents.get(doc_id)
    if card is None:
        return HTMLResponse(f"<h1>Not found: {doc_id}</h1>", status_code=404)

    is_desync = state.is_desync(card)
    hash_map = build_hash_map(state.index.documents)
    copies = [did for did in hash_map.get(card.content_hash, []) if did != doc_id]

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "card.html",
        {
            "request": request,
            "card": card,
            "is_desync": is_desync,
            "copies": copies,
            "doc_types": state.doc_types,
            "quote": quote,
        },
    )


@router.get("/read/{doc_id:path}", response_class=HTMLResponse)
async def read_page(
    request: Request,
    doc_id: str,
    section: str | None = None,
) -> Any:
    """Document reader page with markdown rendering."""
    state = get_state(request)
    card = state.index.documents.get(doc_id)
    if card is None:
        return HTMLResponse(f"<h1>Not found: {doc_id}</h1>", status_code=404)

    result = state.read_document(doc_id, section=section)
    if "error" in result:
        return HTMLResponse(f"<h1>Error: {result['error']}</h1>", status_code=400)

    content: str = result["content"]
    if card.rel_path.endswith(".md"):
        rendered_html: str = str(mistune.html(content))
    else:
        rendered_html = f"<pre><code>{_escape_html(content)}</code></pre>"

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "doc.html",
        {
            "request": request,
            "card": card,
            "rendered_html": rendered_html,
            "total_lines": result["total_lines"],
            "returned_lines": result["returned_lines"],
            "section": section,
            "available_sections": result.get("available_sections") or [],
            "quote": quote,
        },
    )


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
