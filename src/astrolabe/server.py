"""MCP server for astrolabe — knowledge layer across projects."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from mcp.server.fastmcp import FastMCP

from astrolabe import __version__
from astrolabe.chunker import chunk_file
from astrolabe.config import load_config, load_doc_types_full
from astrolabe.embeddings import EmbeddingBackend, EmbeddingResult, is_embeddings_available
from astrolabe.index import ReindexStats, build_hash_map, build_index, reindex, update_card
from astrolabe.models import (
    AppConfig,
    CosmosResponse,
    DocCard,
    IndexData,
    ProjectSummary,
    TypeSummary,
)
from astrolabe.reader import read_file
from astrolabe.search import hybrid_search, search
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
_embedding_backend: EmbeddingBackend | None = None


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
        embeddings=config.embeddings,
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


def _init_embeddings(config: AppConfig) -> None:
    """Initialize embedding backend if embeddings are enabled."""
    global _embedding_backend

    _embedding_backend = None

    if not config.embeddings:
        return

    if not is_embeddings_available():
        logger.warning(
            "embeddings=true in config but chromadb is not installed. "
            "Install with: pip install astrolabe-mcp[embeddings]. "
            "Falling back to stem-only search."
        )
        return

    from astrolabe.embeddings import create_embedding_backend

    embeddings_dir = config.embeddings_dir or Path("runtime/.chromadb")
    _embedding_backend = create_embedding_backend(embeddings_dir)
    logger.info("Embedding backend created at %s", embeddings_dir)


def _sync_embeddings(
    index: IndexData,
    stats: "ReindexStats",
    config: AppConfig,
    mode: str,
) -> None:
    """Sync embeddings after reindex using manifest-based diff.

    Compares index state with embedding manifest to determine what needs
    embedding. Works correctly for first launch (empty manifest), partial
    embeddings, and incremental updates.
    """
    if _embedding_backend is None:
        return

    if mode == "rebuild":
        try:
            _embedding_backend.clear()
        except Exception as exc:
            logger.error("Failed to clear embeddings during rebuild: %s", exc)
            return

    # Load manifest and diff with current index
    manifest = _embedding_backend.load_manifest()

    to_embed: dict[str, DocCard] = {}
    for doc_id, card in index.documents.items():
        if doc_id not in manifest or manifest[doc_id] != card.content_hash:
            to_embed[doc_id] = card

    to_remove = set(manifest.keys()) - set(index.documents.keys())

    if not to_embed and not to_remove:
        logger.info("Embedding sync: nothing to do")
        return

    logger.info(
        "Embedding sync: %d to embed, %d to remove",
        len(to_embed),
        len(to_remove),
    )

    # Embed new/changed documents
    for doc_id, card in to_embed.items():
        project_path = config.all_projects.get(card.project)
        if project_path is None:
            continue

        file_path = project_path / card.rel_path
        if not file_path.exists():
            continue

        chunks = chunk_file(file_path, max_file_size_kb=config.max_file_size_kb)
        if not chunks:
            # Binary/media/oversized — not embeddable, mark in manifest to skip next time
            manifest[doc_id] = card.content_hash
            continue

        try:
            _embedding_backend.upsert_document(
                doc_id,
                chunks,
                {"doc_id": doc_id, "project": card.project, "content_hash": card.content_hash},
            )
            manifest[doc_id] = card.content_hash
            stats.embedded += 1
        except Exception as exc:
            logger.warning("Failed to embed %s: %s", doc_id, exc)
            stats.embedding_errors += 1

    # Remove embeddings for deleted documents
    for doc_id in to_remove:
        try:
            _embedding_backend.remove_document(doc_id)
        except Exception as exc:
            logger.warning("Failed to remove embedding for %s: %s", doc_id, exc)
        manifest.pop(doc_id, None)

    _embedding_backend.save_manifest(manifest)


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

    # Create embedding backends if configured
    _init_embeddings(_config)

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
        _save_index()
        # Note: embeddings sync deferred to first reindex_tool() or deep_search() call
        # to avoid slow ChromaDB loading at startup
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

    Returns all document types with descriptions, examples, and conventions.
    Use this before enriching cards with update_index_tool to pick the right type.
    """
    _get_state()  # ensure initialized
    return _doc_types_full


@mcp.tool()
def get_cosmos() -> dict:  # type: ignore[type-arg]
    """Get the full catalog overview: projects, types, index health. Start here.

    Returns project list, document type stats, enrichment coverage, and sync status.
    Use as the first call in a session to understand what's indexed.
    Check desync_documents — if > 0, files missing on disk (run reindex).
    Check stale_documents — if > 0, content changed since enrichment (re-enrich).
    Check diverged_documents — if > 0, a duplicate group split; ask the user before
    resolving (use list_docs(diverged=true)).
    Then use list_docs/search_docs to drill into specific projects or topics.
    """
    config, index = _get_state()

    # Per-project stats
    project_stats: dict[str, dict[str, int]] = {}
    for pid in config.all_projects:
        project_stats[pid] = {
            "doc_count": 0,
            "enriched_count": 0,
            "stale_count": 0,
            "empty_count": 0,
            "desync_count": 0,
            "diverged_count": 0,
        }

    total = len(index.documents)
    enriched = 0
    stale = 0
    empty = 0
    desync = 0
    diverged = 0
    type_counts: dict[str, int] = {}

    for card in index.documents.values():
        is_diverged = bool(card.diverged_from)
        if card.project in project_stats:
            project_stats[card.project]["doc_count"] += 1
            if not card.is_empty:
                project_stats[card.project]["enriched_count"] += 1
            if card.is_stale:
                project_stats[card.project]["stale_count"] += 1
            if card.is_empty:
                project_stats[card.project]["empty_count"] += 1

            if _is_desync(card, config):
                desync += 1
                project_stats[card.project]["desync_count"] += 1

            if is_diverged:
                project_stats[card.project]["diverged_count"] += 1

        if is_diverged:
            diverged += 1

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
            stale_count=stats["stale_count"],
            empty_count=stats["empty_count"],
            desync_count=stats["desync_count"],
            diverged_count=stats["diverged_count"],
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

    # Embedding stats
    embeddings_enabled = _embedding_backend is not None
    embedded_chunks = _embedding_backend.count if _embedding_backend is not None else 0

    resp = CosmosResponse(
        server_version=__version__,
        indexed_at=index.indexed_at,
        total_documents=total,
        enriched_documents=enriched,
        stale_documents=stale,
        empty_documents=empty,
        desync_documents=desync,
        diverged_documents=diverged,
        embeddings_enabled=embeddings_enabled,
        embedded_chunks=embedded_chunks,
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
    diverged: bool | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:  # type: ignore[type-arg]
    """List document cards with optional filters and pagination.

    Tip: use get_cosmos() first for project overview and counts.
    Narrow by project/type before browsing large catalogs.

    Args:
        project: Filter by project ID.
        type: Filter by document type (e.g. "reference", "spec", "task").
        stale: If true, return cards that need enrichment — both empty (never enriched)
            and stale (enriched but file changed since).
        desync: If true, return only cards whose files are missing on disk
            (deleted or not synced from another machine). Use with project filter
            to diagnose desync in a specific project.
        diverged: If true, return only cards that used to share content with others
            but were edited in one place (non-empty diverged_from). Review each and
            call accept_divergence(doc_id) to accept the split, or sync the other
            copies so next reindex reconverges them.
        limit: Max cards to return. Default from config (~50).
        offset: Skip first N cards (for pagination).
    """
    config, index = _get_state()
    effective_limit = limit if limit is not None else config.default_list_limit
    offset = max(0, offset)

    # Collect all filtered cards + counts for hints
    filtered: list[DocCard] = []
    type_counts: dict[str | None, int] = {}
    project_counts: dict[str, int] = {}

    for card in index.documents.values():
        if project is not None and card.project != project:
            continue
        if type is not None and card.type != type:
            continue
        if stale is True and not (card.is_stale or card.is_empty):
            continue
        if desync is True and not _is_desync(card, config):
            continue
        if diverged is True and not card.diverged_from:
            continue

        filtered.append(card)
        type_counts[card.type] = type_counts.get(card.type, 0) + 1
        project_counts[card.project] = project_counts.get(card.project, 0) + 1

    total = len(filtered)
    page = filtered[offset : offset + effective_limit]

    hash_map = build_hash_map(index.documents)
    result = []
    for c in page:
        entry: dict[str, object] = {
            "doc_id": c.doc_id,
            "project": c.project,
            "type": c.type,
            "filename": c.filename,
            "summary": c.summary,
            "keywords": c.keywords,
        }
        if c.content_hash in hash_map:
            entry["has_copies"] = True
        if c.diverged_from:
            entry["diverged_from"] = c.diverged_from
        result.append(entry)

    envelope: dict[str, object] = {
        "total": total,
        "limit": effective_limit,
        "offset": offset,
        "result": result,
    }

    # Adaptive hint when truncated
    if total > offset + effective_limit:
        hint_parts = [f"Showing {len(result)} of {total}."]

        # Applied filters
        applied = []
        if project is not None:
            applied.append(f"project={project}")
        if type is not None:
            applied.append(f"type={type}")
        if stale is True:
            applied.append("stale=true")
        if desync is True:
            applied.append("desync=true")
        if diverged is True:
            applied.append("diverged=true")
        hint_parts.append(f"Filters: {', '.join(applied)}" if applied else "Filters: none")

        # Suggest narrowing by unused axis
        if project is None and type is None:
            top_projects = sorted(project_counts.items(), key=lambda x: -x[1])[:5]
            top_types = sorted(type_counts.items(), key=lambda x: -x[1])[:5]
            hint_parts.append(
                "Narrow by project: " + ", ".join(f"{p}({n})" for p, n in top_projects)
            )
            hint_parts.append("Narrow by type: " + ", ".join(f"{t}({n})" for t, n in top_types))
        elif project is not None and type is None:
            top_types = sorted(type_counts.items(), key=lambda x: -x[1])[:5]
            hint_parts.append("Narrow by type: " + ", ".join(f"{t}({n})" for t, n in top_types))
        elif type is not None and project is None:
            top_projects = sorted(project_counts.items(), key=lambda x: -x[1])[:5]
            hint_parts.append(
                "Narrow by project: " + ", ".join(f"{p}({n})" for p, n in top_projects)
            )

        hint_parts.append(f"Next page: offset={offset + effective_limit}")
        envelope["hint"] = " ".join(hint_parts)
    elif offset >= total and total > 0:
        envelope["hint"] = f"No results at offset={offset}. Total matching: {total}. Try offset=0."

    return envelope


@mcp.tool()
def search_docs(
    query: str,
    project: str | None = None,
    type: str | None = None,
    max_results: int | None = None,
) -> dict:  # type: ignore[type-arg]
    """Search documents by query with relevance ranking.

    Searches across filename, keywords, headings, and summary.
    Returns top results sorted by relevance. Use project/type filters
    or more specific queries to narrow results.

    Args:
        query: Search query (e.g. "telegram api", "architecture guide").
        project: Filter by project ID.
        type: Filter by document type.
        max_results: Max results to return. Default from config (~20).
    """
    config, index = _get_state()
    effective_max = max_results if max_results is not None else config.default_search_limit

    type_boosts = {
        name: entry.get("search_boost", 1.0)
        for name, entry in _doc_types_full.items()
        if "search_boost" in entry
    }

    results = search(
        index.documents.values(), query, project=project, type=type, type_boosts=type_boosts
    )

    # Dedup by content_hash: keep first (highest relevance) per hash
    hash_map = build_hash_map(index.documents)
    if hash_map:
        seen_hashes: set[str] = set()
        deduped = []
        for r in results:
            card = index.documents.get(r.doc_id)
            if card and card.content_hash in hash_map:
                if card.content_hash in seen_hashes:
                    continue
                seen_hashes.add(card.content_hash)
            deduped.append(r)
        results = deduped

    total = len(results)
    page = results[:effective_max]

    result = [
        {
            "doc_id": r.doc_id,
            "project": r.project,
            "type": r.type,
            "filename": r.filename,
            "summary": r.summary,
            "keywords": r.keywords,
            "relevance": r.relevance,
        }
        for r in page
    ]

    envelope: dict[str, object] = {
        "total": total,
        "max_results": effective_max,
        "result": result,
    }

    if total > effective_max:
        hint_parts = [f"Showing top {effective_max} of {total} matches."]
        suggestions = []
        if project is None:
            suggestions.append("project=...")
        if type is None:
            suggestions.append("type=...")
        suggestions.append("more specific query")
        hint_parts.append(f"Try: {', '.join(suggestions)} to narrow results.")
        envelope["hint"] = " ".join(hint_parts)
    elif total < config.semantic_hint_threshold and _embedding_backend is not None:
        envelope["hint"] = (
            f"Only {total} keyword matches. "
            "Try deep_search(query) for semantic search over file content."
        )

    return envelope


@mcp.tool()
def deep_search(
    query: str,
    project: str | None = None,
    max_results: int | None = None,
) -> dict:  # type: ignore[type-arg]
    """Semantic search over file content using embeddings. Slower but finds by meaning.

    Use when search_docs() returns too few results or when searching for concepts
    rather than exact terms. Requires embeddings=true in config.

    Unlike search_docs (fast keyword matching on enriched cards), this tool searches
    actual file content semantically — works even for unenriched documents.

    Args:
        query: Search query — works best with descriptive phrases.
        project: Filter by project ID.
        max_results: Max results to return. Default from config (~20).
    """
    config, index = _get_state()
    effective_max = max_results if max_results is not None else config.default_search_limit

    if _embedding_backend is None:
        if not config.embeddings:
            return {
                "error": "Semantic search is not enabled",
                "hint": (
                    'Set "embeddings": true in config.json '
                    "and install: pip install astrolabe-mcp[embeddings]"
                ),
            }
        return {
            "error": "chromadb is not installed",
            "hint": "Install with: pip install astrolabe-mcp[embeddings]",
        }

    # Query embedding backend
    n_chunks = max(30, effective_max * 2)
    embedding_results: list[EmbeddingResult] = _embedding_backend.query(
        query, n_results=n_chunks, project=project
    )

    # Use hybrid_search with embedding results (stem + embed combined)
    results = hybrid_search(
        index.documents.values(),
        query,
        embedding_results,
        project=project,
    )

    # Dedup by content_hash
    hash_map = build_hash_map(index.documents)
    if hash_map:
        seen_hashes: set[str] = set()
        deduped = []
        for r in results:
            card = index.documents.get(r.doc_id)
            if card and card.content_hash in hash_map:
                if card.content_hash in seen_hashes:
                    continue
                seen_hashes.add(card.content_hash)
            deduped.append(r)
        results = deduped

    total = len(results)
    page = results[:effective_max]

    result = [
        {
            "doc_id": r.doc_id,
            "project": r.project,
            "type": r.type,
            "filename": r.filename,
            "summary": r.summary,
            "keywords": r.keywords,
            "relevance": r.relevance,
        }
        for r in page
    ]

    envelope: dict[str, object] = {
        "total": total,
        "max_results": effective_max,
        "result": result,
        "hint": (
            "Semantic search results (by meaning, not exact words). "
            "For exact keyword matching use search_docs(query)."
        ),
    }

    return envelope


@mcp.tool()
def get_card(doc_id: str) -> dict:  # type: ignore[type-arg]
    """Get index card for a document — type, summary, keywords, headings, timestamps.

    No file content. Use this to inspect metadata before deciding to read_doc().
    Includes full timestamps (modified, enriched_at) not shown in list/search results.
    Call get_card() first, then read_doc() with section= for large files.

    Args:
        doc_id: Document ID in format "project::rel_path".
    """
    _, index = _get_state()

    if doc_id not in index.documents:
        return {"error": f"Document not found: {doc_id}", "hint": "Check doc_id or run reindex()."}

    card = index.documents[doc_id]
    result: dict[str, object] = {
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
        "content_hash": card.content_hash,
        "enriched_content_hash": card.enriched_content_hash,
        "stale": card.is_stale,
    }

    # Add copies if this document has duplicates in other locations
    hash_map = build_hash_map(index.documents)
    if card.content_hash in hash_map:
        result["copies"] = [did for did in hash_map[card.content_hash] if did != doc_id]

    # Add divergence info if this card was edited out of a former duplicate group
    if card.diverged_from:
        result["diverged_from"] = list(card.diverged_from)
        result["hint"] = (
            "This card diverged from its former copies. Ask the user whether to "
            "accept_divergence(doc_id) (keep the split) or sync the listed siblings "
            "(next reindex will reconverge them)."
        )

    return result


@mcp.tool()
def read_doc(
    doc_id: str,
    section: str | None = None,
    range: str | None = None,
) -> dict:  # type: ignore[type-arg]
    """Read document content from disk. Returns full file, a section by heading, or a line range.

    Use after search_docs() or list_docs() to read what you found.
    For large files: call get_card() first to see headings, then use section= for targeted read.
    If truncated, response includes available_sections and a hint with navigation options.

    Args:
        doc_id: Document ID in format "project::rel_path".
        section: Heading name to extract (from card headings or available_sections).
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
        sections = result.available_sections or []
        if sections:
            sections_str = ", ".join(sections)
            resp["hint"] = (
                f"Showing lines 1-{result.returned_lines} of {result.total_lines}. "
                f"Available sections: [{sections_str}]. "
                f"Use section='...' or range='start-end' for targeted read."
            )
        else:
            resp["hint"] = (
                f"Showing lines 1-{result.returned_lines} of {result.total_lines}. "
                f"Use range='start-end' for targeted read."
            )
        resp["available_sections"] = sections
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
    """Rescan filesystem and update the index.

    Call when files were added, removed, or renamed.
    Cards from projects not in local config are always preserved (pass-through).
    After reindex, use list_docs(stale=true) to find cards needing enrichment.

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

    # Always reload from storage to pick up changes from web UI or other processes
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

    # Reinitialize embedding backends (config may have changed)
    _init_embeddings(config)

    # Sync embeddings for new/stale/removed documents
    try:
        _sync_embeddings(_index, stats, config, mode=reindex_mode)
    except Exception as exc:
        logger.error("Embedding sync failed (index saved successfully): %s", exc)

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
    if stats.embedded > 0:
        result["embedded"] = stats.embedded
    if stats.embedding_errors > 0:
        result["embedding_errors"] = stats.embedding_errors
    if stats.auto_transferred:
        result["auto_transferred"] = [
            {"from": old_id, "to": new_id} for old_id, new_id in stats.auto_transferred
        ]
    if stats.ambiguous_moves:
        result["ambiguous_moves"] = stats.ambiguous_moves
    if stats.new_divergences:
        result["new_divergences"] = stats.new_divergences
        result["hint"] = (
            f"{len(stats.new_divergences)} duplicate group(s) split during this reindex. "
            "Ask the user: accept_divergence(doc_id) for an intentional fork, "
            "or edit the other copies so next reindex reconverges them."
        )
    return result


@mcp.tool()
def accept_divergence(doc_id: str) -> dict:  # type: ignore[type-arg]
    """Accept that a card has intentionally drifted from its former duplicate group.

    Clears `diverged_from` on the target card. After acceptance the card is
    treated as an independent document — it keeps its own enrichment cycle and
    appears separately in search (no dedup with former siblings).

    When NOT to use this: if the edit was a one-off and you want the other copies
    synced, just edit them to match — the next reindex will reconverge the hashes
    and clear `diverged_from` automatically.

    Args:
        doc_id: Document ID (format "project::rel_path") of the diverged card.
    """
    _, index = _get_state()

    if doc_id not in index.documents:
        return {"error": f"Document not found: {doc_id}", "hint": "Check doc_id or run reindex()."}

    card = index.documents[doc_id]
    if not card.diverged_from:
        return {
            "error": f"No divergence to accept: {doc_id}",
            "hint": "The card is not flagged as diverged. Nothing to do.",
        }

    cleared = list(card.diverged_from)
    card.diverged_from = None

    storage = _get_storage_for_project(card.project)
    storage.save_card(card, index.indexed_at)

    return {"ok": True, "doc_id": doc_id, "cleared_from": cleared}


def main() -> None:
    """Entry point for the MCP server."""
    logging.basicConfig(level=logging.INFO)
    _init()
    mcp.run()


if __name__ == "__main__":
    main()
