"""HTMX API routes — return HTML fragments."""

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from astrolabe.index import build_hash_map
from astrolabe.web.app import get_state

router = APIRouter()


@router.get("/cards", response_class=HTMLResponse)
async def cards_partial(
    request: Request,
    project: str | None = None,
    type: str | None = None,
    stale: bool = False,
    empty: bool = False,
    desync: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Filtered card list partial for HTMX swap."""
    state = get_state(request)
    cards, total = state.list_cards(
        project=project,
        type=type,
        stale=stale,
        empty=empty,
        desync=desync,
        limit=limit,
        offset=offset,
    )
    hash_map = build_hash_map(state.index.documents)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/card_list.html",
        {
            "request": request,
            "cards": cards,
            "total": total,
            "limit": limit,
            "offset": offset,
            "quote": quote,
            "state": state,
            "hash_map": hash_map,
            "filter_project": project,
            "filter_type": type,
            "filter_stale": stale,
            "filter_empty": empty,
            "filter_desync": desync,
        },
    )


@router.get("/cards/{doc_id:path}/edit", response_class=HTMLResponse)
async def card_edit_form(request: Request, doc_id: str) -> Any:
    """Return edit form partial for a card."""
    state = get_state(request)
    card = state.index.documents.get(doc_id)
    if card is None:
        return HTMLResponse("Card not found", status_code=404)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/card_fields.html",
        {
            "request": request,
            "card": card,
            "doc_types": state.doc_types,
            "edit_mode": True,
            "quote": quote,
        },
    )


@router.post("/cards/{doc_id:path}/save", response_class=HTMLResponse)
async def card_save(
    request: Request,
    doc_id: str,
    type: str = Form(""),
    summary: str = Form(""),
    keywords: str = Form(""),
    headings: str = Form(""),
) -> Any:
    """Save card edit and return updated view partial."""
    state = get_state(request)

    # Parse form values
    card_type = type.strip() if type.strip() else None
    card_summary = summary.strip() if summary.strip() else None
    card_keywords = (
        [k.strip() for k in keywords.split(",") if k.strip()] if keywords.strip() else None
    )
    card_headings = (
        [h.strip() for h in headings.split(",") if h.strip()] if headings.strip() else None
    )

    # Validate type
    if card_type and state.doc_types and card_type not in state.doc_types:
        available = sorted(state.doc_types.keys())
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "partials/toast.html",
            {
                "request": request,
                "message": f"Unknown type '{card_type}'. Available: {', '.join(available)}",
                "level": "error",
            },
        )

    try:
        card = state.do_update_card(
            doc_id,
            type=card_type,
            summary=card_summary,
            keywords=card_keywords,
            headings=card_headings,
        )
    except KeyError:
        return HTMLResponse("Card not found", status_code=404)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/card_fields.html",
        {
            "request": request,
            "card": card,
            "doc_types": state.doc_types,
            "edit_mode": False,
            "quote": quote,
            "toast_message": "Card updated",
            "toast_level": "success",
            "toast_reload": True,
        },
    )


@router.get("/cards/{doc_id:path}/type-edit", response_class=HTMLResponse)
async def type_edit(request: Request, doc_id: str) -> Any:
    """Return inline type selector (open listbox) for card list."""
    state = get_state(request)
    card = state.index.documents.get(doc_id)
    if card is None:
        return HTMLResponse("Card not found", status_code=404)

    doc_id_enc = quote(doc_id, safe="")
    save_url = f"/api/cards/{doc_id_enc}/type-save"
    badge_url = f"/api/cards/{doc_id_enc}/type-badge"

    options = ['<option value="">— none —</option>']
    for t_name in sorted(state.doc_types.keys()):
        sel = " selected" if card.type == t_name else ""
        options.append(f'<option value="{t_name}"{sel}>{t_name}</option>')

    size = min(len(state.doc_types) + 1, 10)
    select_html = (
        f'<select class="inline-type-select" size="{size}" autofocus '
        f"onchange=\"htmx.ajax('POST', '{save_url}', "
        f"{{target:this.closest('.type-cell'), swap:'innerHTML', "
        f'values:{{type:this.value}}}})" '
        f'onblur="var s=this; setTimeout(function(){{ if(s.parentNode) '
        f"htmx.ajax('GET', '{badge_url}', "
        f"{{target:s.closest('.type-cell'), swap:'innerHTML'}})}}, 150)\" "
        f"onkeydown=\"if(event.key==='Escape') this.blur()\" "
        f">{''.join(options)}</select>"
    )
    return HTMLResponse(select_html)


@router.get("/cards/{doc_id:path}/type-badge", response_class=HTMLResponse)
async def type_badge(request: Request, doc_id: str) -> Any:
    """Return current type badge (for cancel)."""
    state = get_state(request)
    card = state.index.documents.get(doc_id)
    if card is None:
        return HTMLResponse("Card not found", status_code=404)
    return HTMLResponse(_type_badge_html(doc_id, card.type))


@router.post("/cards/{doc_id:path}/type-save", response_class=HTMLResponse)
async def type_save(request: Request, doc_id: str, type: str = Form("")) -> Any:
    """Save type from inline selector, return badge."""
    state = get_state(request)
    card_type = type.strip() or None

    if card_type and state.doc_types and card_type not in state.doc_types:
        return HTMLResponse("<em>invalid</em>")

    try:
        card = state.do_update_card(doc_id, type=card_type)
    except KeyError:
        return HTMLResponse("Card not found", status_code=404)

    return HTMLResponse(_type_badge_html(doc_id, card.type))


def _type_badge_html(doc_id: str, card_type: str | None) -> str:
    """Generate clickable type badge HTML."""
    doc_id_enc = quote(doc_id, safe="")
    if card_type:
        return (
            f'<span class="badge type-click" '
            f'hx-get="/api/cards/{doc_id_enc}/type-edit" '
            f'hx-target="closest .type-cell" hx-swap="innerHTML" '
            f'title="Click to change type">{card_type}</span>'
        )
    return (
        f'<em class="type-click" '
        f'hx-get="/api/cards/{doc_id_enc}/type-edit" '
        f'hx-target="closest .type-cell" hx-swap="innerHTML" '
        f'title="Click to set type">-</em>'
    )


@router.post("/cards/{doc_id:path}/dismiss-stale", response_class=HTMLResponse)
async def dismiss_stale(request: Request, doc_id: str) -> Any:
    """Mark stale card as reviewed — update enriched_at/hash without changing enrichment."""
    state = get_state(request)
    try:
        state.do_update_card(doc_id)
    except KeyError:
        return HTMLResponse("Card not found", status_code=404)
    return HTMLResponse('<span class="ok-mark">ok</span>')


@router.post("/cards/{doc_id:path}/cancel", response_class=HTMLResponse)
async def card_cancel(request: Request, doc_id: str) -> Any:
    """Cancel edit and return view partial."""
    state = get_state(request)
    card = state.index.documents.get(doc_id)
    if card is None:
        return HTMLResponse("Card not found", status_code=404)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/card_fields.html",
        {
            "request": request,
            "card": card,
            "doc_types": state.doc_types,
            "edit_mode": False,
            "quote": quote,
        },
    )


@router.post("/search", response_class=HTMLResponse)
async def search_partial(
    request: Request,
    query: str = Form(""),
    project: str = Form(""),
    type: str = Form(""),
) -> Any:
    """Search results partial for HTMX."""
    state = get_state(request)

    if not query.strip():
        return HTMLResponse("<p>Enter a search query.</p>")

    results = state.search_cards(
        query.strip(),
        project=project.strip() or None,
        type=type.strip() or None,
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/search_results.html",
        {"request": request, "results": results, "query": query, "quote": quote},
    )


@router.post("/reindex", response_class=HTMLResponse)
async def reindex_action(
    request: Request,
    mode: str = Form("update"),
    project: str = Form(""),
) -> Any:
    """Trigger reindex and return toast with results."""
    state = get_state(request)

    if mode not in ("update", "clean", "rebuild"):
        return HTMLResponse(f"Invalid mode: {mode}", status_code=400)

    stats = state.do_reindex(
        project=project.strip() or None,
        mode=mode,
    )

    if "error" in stats:
        message = str(stats["error"])
        level = "error"
    else:
        message = (
            f"Reindex ({mode}): scanned {stats['scanned']}, "
            f"new {stats['new']}, removed {stats['removed']}, "
            f"stale {stats['stale']}, {stats['duration_ms']}ms"
        )
        level = "success"

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/toast.html",
        {"request": request, "message": message, "level": level, "reload": True},
    )


@router.post("/refresh", response_class=HTMLResponse)
async def refresh_action(request: Request) -> Any:
    """Reload index from storage."""
    state = get_state(request)
    state.reload()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "partials/toast.html",
        {
            "request": request,
            "message": f"Reloaded: {len(state.index.documents)} documents",
            "level": "success",
            "reload": True,
        },
    )
