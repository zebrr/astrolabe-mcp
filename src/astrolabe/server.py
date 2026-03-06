"""MCP server for astrolabe — knowledge layer across projects."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from astrolabe.config import load_config, load_doc_types
from astrolabe.index import build_index, load_index, reindex, save_index, update_card
from astrolabe.models import AppConfig, CosmosResponse, IndexData, ProjectSummary, TypeSummary
from astrolabe.reader import read_file
from astrolabe.search import search

logger = logging.getLogger(__name__)

mcp = FastMCP("astrolabe")

# Global state
_config: AppConfig | None = None
_index: IndexData | None = None
_doc_types: dict[str, str] = {}


def _init() -> tuple[AppConfig, IndexData]:
    """Initialize config and index. Called on startup."""
    global _config, _index, _doc_types

    config_path_str = os.environ.get("ASTROLABE_CONFIG", "runtime/config.json")
    config_path = Path(config_path_str).resolve()

    _config = load_config(config_path)
    _doc_types = load_doc_types(config_path.parent / "doc_types.yaml")

    existing = load_index(_config.index_path)
    if existing is not None:
        _index, stats = reindex(_config, existing)
        logger.info("Reindex on startup: %s", stats)
    else:
        _index = build_index(_config)
        logger.info("Built fresh index: %d documents", len(_index.documents))

    save_index(_index, _config.index_path)
    return _config, _index


def _get_state() -> tuple[AppConfig, IndexData]:
    """Get current state, initializing if needed."""
    global _config, _index
    if _config is None or _index is None:
        return _init()
    return _config, _index


@mcp.tool()
def get_cosmos() -> dict:  # type: ignore[type-arg]
    """Get the full catalog: projects, document types, index stats.

    Call this at the start of a session to understand what's available.
    Returns project list, document type stats, and index coverage.
    """
    config, index = _get_state()

    # Per-project stats
    project_stats: dict[str, dict[str, int]] = {}
    for pid in config.projects:
        project_stats[pid] = {"doc_count": 0, "enriched_count": 0}

    total = len(index.documents)
    enriched = 0
    stale = 0
    empty = 0
    type_counts: dict[str, int] = {}

    for card in index.documents.values():
        if card.project in project_stats:
            project_stats[card.project]["doc_count"] += 1
            if not card.is_empty:
                project_stats[card.project]["enriched_count"] += 1

        if card.is_empty:
            empty += 1
        elif card.is_stale:
            stale += 1
            enriched += 1
        else:
            enriched += 1

        if card.type is not None:
            type_counts[card.type] = type_counts.get(card.type, 0) + 1

    projects = [
        ProjectSummary(
            id=pid,
            doc_count=stats["doc_count"],
            enriched_count=stats["enriched_count"],
            last_indexed=index.indexed_at,
        )
        for pid, stats in project_stats.items()
    ]

    document_types = [
        TypeSummary(
            type=t,
            description=_doc_types.get(t, ""),
            count=c,
        )
        for t, c in sorted(type_counts.items())
    ]

    resp = CosmosResponse(
        server_version="0.2.0",
        indexed_at=index.indexed_at,
        total_documents=total,
        enriched_documents=enriched,
        stale_documents=stale,
        empty_documents=empty,
        projects=projects,
        document_types=document_types,
    )
    return resp.model_dump(mode="json")


@mcp.tool()
def list_docs(
    project: str | None = None,
    type: str | None = None,
    stale: bool | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    """List document cards with optional filters.

    Args:
        project: Filter by project ID.
        type: Filter by document type.
        stale: If true, only return stale or empty cards (need enrichment).
    """
    _, index = _get_state()

    results = []
    for card in index.documents.values():
        if project is not None and card.project != project:
            continue
        if type is not None and card.type != type:
            continue
        if stale is True and not (card.is_stale or card.is_empty):
            continue

        results.append(
            {
                "doc_id": card.doc_id,
                "project": card.project,
                "type": card.type,
                "filename": card.filename,
                "summary": card.summary,
                "keywords": card.keywords,
                "modified": card.modified.isoformat(),
                "enriched_at": card.enriched_at.isoformat() if card.enriched_at else None,
            }
        )

    return results


@mcp.tool()
def search_docs(
    query: str,
    project: str | None = None,
    type: str | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    """Search documents by query with relevance ranking.

    Searches across filename, keywords, headings, and summary.
    Returns results sorted by relevance.

    Args:
        query: Search query (e.g. "telegram api", "architecture guide").
        project: Filter by project ID.
        type: Filter by document type.
    """
    _, index = _get_state()
    results = search(index.documents.values(), query, project=project, type=type)
    return [r.model_dump(mode="json") for r in results]


@mcp.tool()
def read_doc(doc_id: str) -> dict:  # type: ignore[type-arg]
    """Get full card metadata for a specific document (no file content).

    Use this to inspect a document's details before reading its content.

    Args:
        doc_id: Document ID in format "project::rel_path".
    """
    _, index = _get_state()

    if doc_id not in index.documents:
        return {"error": f"Document not found: {doc_id}", "hint": "Check doc_id or run reindex()."}

    card = index.documents[doc_id]
    return {
        "doc_id": card.doc_id,
        "project": card.project,
        "filename": card.filename,
        "rel_path": card.rel_path,
        "size": card.size,
        "modified": card.modified.isoformat(),
        "type": card.type,
        "headings": card.headings,
        "summary": card.summary,
        "keywords": card.keywords,
        "enriched_at": card.enriched_at.isoformat() if card.enriched_at else None,
    }


@mcp.tool()
def get_doc(
    doc_id: str,
    section: str | None = None,
    range: str | None = None,
) -> dict:  # type: ignore[type-arg]
    """Read file content. Full file, by section heading, or by line range.

    Args:
        doc_id: Document ID in format "project::rel_path".
        section: Heading name to extract specific section.
        range: Line range like "1-50" (1-based inclusive).
    """
    config, index = _get_state()

    if doc_id not in index.documents:
        return {"error": f"Document not found: {doc_id}", "hint": "Check doc_id or run reindex()."}

    card = index.documents[doc_id]
    project_path = config.projects.get(card.project)
    if project_path is None:
        return {"error": f"Project not found in config: {card.project}"}

    file_path = project_path / card.rel_path
    if not file_path.exists():
        return {
            "error": f"File not found: {card.rel_path}",
            "hint": "File may have been deleted. Run reindex() to update.",
        }

    try:
        result = read_file(
            file_path,
            max_size_kb=config.max_file_size_kb,
            section=section,
            line_range=range,
        )
    except ValueError as e:
        return {"error": str(e)}

    resp: dict[str, object] = {
        "doc_id": doc_id,
        "content": result.content,
        "total_lines": result.total_lines,
        "returned_lines": result.returned_lines,
    }
    if result.section is not None:
        resp["section"] = result.section
    if result.truncated:
        resp["truncated"] = True
        resp["warning"] = f"File exceeds {config.max_file_size_kb}KB. Use section or range."
    if result.available_sections is not None:
        resp["available_sections"] = result.available_sections
    return resp


@mcp.tool()
def update_index_tool(
    doc_id: str,
    type: str | None = None,
    summary: str | None = None,
    keywords: list[str] | None = None,
    headings: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Enrich a document card with type, summary, keywords, and headings.

    Call this after reading a document to fill in its metadata.
    Only updates fields that are provided — others remain unchanged.

    Args:
        doc_id: Document ID in format "project::rel_path".
        type: Document type (e.g. "reference", "spec", "task").
        summary: Brief description (2-3 sentences).
        keywords: Search keywords.
        headings: Document headings.
    """
    config, index = _get_state()

    try:
        card = update_card(
            index, doc_id, type=type, summary=summary, keywords=keywords, headings=headings
        )
    except KeyError:
        return {"error": f"Document not found: {doc_id}", "hint": "Check doc_id or run reindex()."}

    save_index(index, config.index_path)

    updated_fields = []
    if type is not None:
        updated_fields.append("type")
    if summary is not None:
        updated_fields.append("summary")
    if keywords is not None:
        updated_fields.append("keywords")
    if headings is not None:
        updated_fields.append("headings")

    return {
        "doc_id": doc_id,
        "status": "updated",
        "enriched_at": card.enriched_at.isoformat() if card.enriched_at else None,
        "updated_fields": updated_fields,
    }


@mcp.tool()
def reindex_tool(project: str | None = None) -> dict:  # type: ignore[type-arg]
    """Rescan filesystem and update index. Preserves enrichment data.

    If index feels stale (new files, deleted files), call this to refresh.
    Enrichment (type, summary, keywords) is preserved — only file metadata updates.

    Args:
        project: Rescan only this project (optional).
    """
    global _index
    config, index = _get_state()

    start = datetime.now(UTC)

    if project is not None:
        # Build a temporary config with just this project
        if project not in config.projects:
            return {"error": f"Project not found: {project}"}
        single_config = AppConfig(
            projects={project: config.projects[project]},
            index_path=config.index_path,
            index_extensions=config.index_extensions,
            ignore_dirs=config.ignore_dirs,
            ignore_files=config.ignore_files,
            max_file_size_kb=config.max_file_size_kb,
        )
        # Keep cards from other projects
        other_cards = {
            doc_id: card for doc_id, card in index.documents.items() if card.project != project
        }
        project_index = IndexData(
            indexed_at=index.indexed_at,
            documents={
                doc_id: card for doc_id, card in index.documents.items() if card.project == project
            },
        )
        new_project_index, stats = reindex(single_config, project_index)
        # Merge back
        merged_docs = {**other_cards, **new_project_index.documents}
        _index = IndexData(indexed_at=new_project_index.indexed_at, documents=merged_docs)
    else:
        _index, stats = reindex(config, index)

    save_index(_index, config.index_path)

    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)

    return {
        "scanned": stats.scanned,
        "new": stats.new,
        "removed": stats.removed,
        "stale": stats.stale,
        "unchanged": stats.unchanged,
        "duration_ms": duration_ms,
    }


def main() -> None:
    """Entry point for the MCP server."""
    logging.basicConfig(level=logging.INFO)
    _init()
    mcp.run()


if __name__ == "__main__":
    main()
