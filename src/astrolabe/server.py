"""MCP server for astrolabe — knowledge layer across projects."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from mcp.server.fastmcp import FastMCP

from astrolabe import __version__
from astrolabe.config import load_config, load_doc_types_full
from astrolabe.index import build_index, reindex, update_card
from astrolabe.models import (
    AppConfig,
    CosmosResponse,
    DocCard,
    IndexData,
    ProjectSummary,
    TypeSummary,
)
from astrolabe.reader import read_file
from astrolabe.search import search
from astrolabe.storage import StorageBackend, create_storage, create_storage_at

logger = logging.getLogger(__name__)

mcp = FastMCP("astrolabe")

# Global state
_config: AppConfig | None = None
_index: IndexData | None = None
_storage: StorageBackend | None = None
_private_storage: StorageBackend | None = None
_doc_types_full: dict[str, dict[str, Any]] = {}
_doc_types: dict[str, str] = {}


def _load_all_doc_types(config: AppConfig, config_path: Path) -> None:
    """Load doc_types.yaml from index dir or config dir into global state."""
    global _doc_types_full, _doc_types
    index_types_path = config.index_dir / "doc_types.yaml"
    config_types_path = config_path.parent / "doc_types.yaml"

    if index_types_path.exists():
        _doc_types_full = load_doc_types_full(index_types_path)
    elif config_types_path.exists():
        _doc_types_full = load_doc_types_full(config_types_path)
    else:
        _doc_types_full = {}

    _doc_types = {name: entry["description"] for name, entry in _doc_types_full.items()}


def _full_scan_config(config: AppConfig) -> AppConfig:
    """Create a config with all_projects for filesystem scanning."""
    if not config.private_projects:
        return config
    return AppConfig(
        projects=config.all_projects,
        index_dir=config.index_dir,
        storage=config.storage,
        index_extensions=config.index_extensions,
        ignore_dirs=config.ignore_dirs,
        ignore_files=config.ignore_files,
        max_file_size_kb=config.max_file_size_kb,
    )


def _save_index() -> None:
    """Split _index into shared/private and save to corresponding storages."""
    assert _config is not None
    assert _index is not None
    assert _storage is not None

    if _private_storage is None:
        # No private config — save everything to shared storage
        _storage.save(_index)
        return

    shared_docs = {}
    private_docs = {}
    for doc_id, card in _index.documents.items():
        if _config.is_private(card.project):
            private_docs[doc_id] = card
        else:
            shared_docs[doc_id] = card

    shared_index = IndexData(indexed_at=_index.indexed_at, documents=shared_docs)
    private_index = IndexData(indexed_at=_index.indexed_at, documents=private_docs)

    _storage.save(shared_index)
    _private_storage.save(private_index)


def _get_storage_for_project(project: str) -> StorageBackend:
    """Return the correct storage backend for a project."""
    assert _config is not None
    assert _storage is not None
    if _private_storage is not None and _config.is_private(project):
        return _private_storage
    return _storage


def _init() -> tuple[AppConfig, IndexData]:
    """Initialize config and index. Called on startup."""
    global _config, _index, _storage, _private_storage

    config_path_str = os.environ.get("ASTROLABE_CONFIG", "runtime/config.json")
    config_path = Path(config_path_str).resolve()

    _config = load_config(config_path)
    _load_all_doc_types(_config, config_path)

    # Create shared storage
    _storage = create_storage(_config)

    # Create private storage if configured
    if _config.private_index_dir is not None:
        _private_storage = create_storage_at(_config.private_index_dir, _config.storage)
    else:
        _private_storage = None

    # Load and merge indexes from both storages
    shared_data = _storage.load()
    private_data = _private_storage.load() if _private_storage is not None else None

    # Merge existing documents
    existing_docs: dict[str, Any] = {}
    indexed_at = datetime.now(UTC)
    if shared_data is not None:
        existing_docs.update(shared_data.documents)
        indexed_at = shared_data.indexed_at
    if private_data is not None:
        existing_docs.update(private_data.documents)

    scan_config = _full_scan_config(_config)
    if existing_docs:
        existing = IndexData(indexed_at=indexed_at, documents=existing_docs)
        _index, stats = reindex(scan_config, existing)
        logger.info("Reindex on startup: %s", stats)
    else:
        _index = build_index(scan_config)
        logger.info("Built fresh index: %d documents", len(_index.documents))

    _save_index()
    return _config, _index


def _get_state() -> tuple[AppConfig, IndexData]:
    """Get current state, initializing if needed."""
    global _config, _index
    if _config is None or _index is None:
        return _init()
    return _config, _index


def _is_desync(card: DocCard, config: AppConfig) -> bool:
    """Check if card's file is missing on disk (project must be configured locally)."""
    if card.project not in config.all_projects:
        return False
    file_path = config.all_projects[card.project] / card.rel_path
    return not file_path.exists()


@mcp.tool()
def get_doc_types() -> dict[str, dict[str, Any]]:
    """Get the document type vocabulary from doc_types.yaml.

    Returns all document types with descriptions and examples.
    Use this to know which types are available before enriching cards.
    """
    _get_state()  # ensure initialized
    return _doc_types_full


@mcp.tool()
def get_cosmos() -> dict:  # type: ignore[type-arg]
    """Get the full catalog: projects, document types, index health.

    Returns project list, document type stats, enrichment coverage, and sync status.
    Check desync_documents — if > 0, some files are missing on disk (run reindex).
    Each project includes desync_count — check which project has missing files.
    Check stale_documents — if > 0, file content changed since enrichment (re-enrich).
    """
    config, index = _get_state()

    # Per-project stats
    project_stats: dict[str, dict[str, int]] = {}
    for pid in config.all_projects:
        project_stats[pid] = {"doc_count": 0, "enriched_count": 0, "desync_count": 0}

    total = len(index.documents)
    enriched = 0
    stale = 0
    empty = 0
    desync = 0
    type_counts: dict[str, int] = {}

    for card in index.documents.values():
        if card.project in project_stats:
            project_stats[card.project]["doc_count"] += 1
            if not card.is_empty:
                project_stats[card.project]["enriched_count"] += 1

            if _is_desync(card, config):
                desync += 1
                project_stats[card.project]["desync_count"] += 1

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
            desync_count=stats["desync_count"],
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
        server_version=__version__,
        indexed_at=index.indexed_at,
        total_documents=total,
        enriched_documents=enriched,
        stale_documents=stale,
        empty_documents=empty,
        desync_documents=desync,
        projects=projects,
        document_types=document_types,
    )
    return resp.model_dump(mode="json")


@mcp.tool()
def list_docs(
    project: str | None = None,
    type: str | None = None,
    stale: bool | None = None,
    desync: bool | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    """List document cards with optional filters.

    Args:
        project: Filter by project ID.
        type: Filter by document type (e.g. "reference", "spec", "task").
        stale: If true, return cards that need enrichment — both empty (never enriched)
            and stale (enriched but file changed since).
        desync: If true, return only cards whose files are missing on disk
            (deleted or not synced from another machine). Use with project filter
            to diagnose desync in a specific project.
    """
    config, index = _get_state()

    results = []
    for card in index.documents.values():
        if project is not None and card.project != project:
            continue
        if type is not None and card.type != type:
            continue
        if stale is True and not (card.is_stale or card.is_empty):
            continue
        if desync is True and not _is_desync(card, config):
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
def get_card(doc_id: str) -> dict:  # type: ignore[type-arg]
    """Get index card for a document — type, summary, keywords, headings, timestamps.

    No file content. Use this to inspect metadata before deciding to read the full file.

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
        "stale": card.is_stale,
    }


@mcp.tool()
def read_doc(
    doc_id: str,
    section: str | None = None,
    range: str | None = None,
) -> dict:  # type: ignore[type-arg]
    """Read document content from disk. Returns full file, a section by heading, or a line range.

    Use after search_docs() or list_docs() to read what you found.

    Args:
        doc_id: Document ID in format "project::rel_path".
        section: Heading name to extract specific section.
        range: Line range like "1-50" (1-based inclusive).
    """
    config, index = _get_state()

    if doc_id not in index.documents:
        return {"error": f"Document not found: {doc_id}", "hint": "Check doc_id or run reindex()."}

    card = index.documents[doc_id]
    project_path = config.all_projects.get(card.project)
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
    For batch enrichment of multiple cards, use the enrich-index skill instead.

    Args:
        doc_id: Document ID in format "project::rel_path".
        type: Document type from doc_types.yaml (e.g. "reference", "spec", "task").
        summary: Brief description (2-3 sentences).
        keywords: Search keywords.
        headings: Document headings.
    """
    _, index = _get_state()

    # Validate type against doc_types vocabulary
    if type is not None and _doc_types and type not in _doc_types:
        available = sorted(_doc_types.keys())
        return {
            "error": f"Unknown type '{type}'. Available types: {available}",
            "hint": "Use get_doc_types() to see the full vocabulary with descriptions.",
        }

    try:
        card = update_card(
            index, doc_id, type=type, summary=summary, keywords=keywords, headings=headings
        )
    except KeyError:
        return {"error": f"Document not found: {doc_id}", "hint": "Check doc_id or run reindex()."}

    storage = _get_storage_for_project(card.project)
    storage.save_card(card, index.indexed_at)

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
def reindex_tool(project: str | None = None, mode: str = "update") -> dict:  # type: ignore[type-arg]
    """Rescan filesystem and update index.

    Call when files were added, removed, or renamed.
    Cards from projects not in local config are always preserved (pass-through).
    Desync = files in index but missing on disk.

    Three modes (escalating):
    - "update" (default): preserve desync cards, preserve enrichment, detect file moves
    - "clean": remove desync cards (deleted/moved files), preserve enrichment
    - "rebuild": remove desync cards AND reset all enrichment (nuclear option)

    Args:
        project: Rescan only this project (optional).
        mode: Reindex mode — "update", "clean", or "rebuild" (default "update").
    """
    global _config, _index, _storage, _private_storage
    if mode not in ("update", "clean", "rebuild"):
        return {"error": f"Invalid mode: {mode}. Use 'update', 'clean', or 'rebuild'."}
    reindex_mode = cast(Literal["update", "clean", "rebuild"], mode)

    # Reload config from disk to pick up any changes
    config_path_str = os.environ.get("ASTROLABE_CONFIG", "runtime/config.json")
    config_path = Path(config_path_str).resolve()
    _config = load_config(config_path)
    _load_all_doc_types(_config, config_path)

    # Recreate both storages in case config changed
    _storage = create_storage(_config)
    if _config.private_index_dir is not None:
        _private_storage = create_storage_at(_config.private_index_dir, _config.storage)
    else:
        _private_storage = None

    config = _config
    if _index is None:
        # Load and merge from both storages
        shared_data = _storage.load()
        private_data = _private_storage.load() if _private_storage is not None else None
        existing_docs: dict[str, Any] = {}
        indexed_at = datetime.now(UTC)
        if shared_data is not None:
            existing_docs.update(shared_data.documents)
            indexed_at = shared_data.indexed_at
        if private_data is not None:
            existing_docs.update(private_data.documents)
        if existing_docs:
            _index = IndexData(indexed_at=indexed_at, documents=existing_docs)
        else:
            _index = build_index(config)
    index = _index

    start = datetime.now(UTC)

    if project is not None:
        # Build a temporary config with just this project
        if project not in config.all_projects:
            return {"error": f"Project not found: {project}"}
        single_config = AppConfig(
            projects={project: config.all_projects[project]},
            index_dir=config.index_dir,
            storage=config.storage,
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
        new_project_index, stats = reindex(single_config, project_index, mode=reindex_mode)
        # Merge back
        merged_docs = {**other_cards, **new_project_index.documents}
        _index = IndexData(indexed_at=new_project_index.indexed_at, documents=merged_docs)
    else:
        # Full reindex uses all_projects
        _index, stats = reindex(_full_scan_config(config), index, mode=reindex_mode)

    _save_index()

    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)

    result: dict[str, object] = {
        "scanned": stats.scanned,
        "new": stats.new,
        "removed": stats.removed,
        "stale": stats.stale,
        "unchanged": stats.unchanged,
        "passthrough": stats.passthrough,
        "desync": stats.desync,
        "duration_ms": duration_ms,
    }
    if stats.auto_transferred:
        result["auto_transferred"] = [
            {"from": old_id, "to": new_id} for old_id, new_id in stats.auto_transferred
        ]
    if stats.ambiguous_moves:
        result["ambiguous_moves"] = stats.ambiguous_moves
    return result


def main() -> None:
    """Entry point for the MCP server."""
    logging.basicConfig(level=logging.INFO)
    _init()
    mcp.run()


if __name__ == "__main__":
    main()
