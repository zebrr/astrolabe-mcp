"""Application state for the web UI — config, index, storage management."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from astrolabe.config import load_config, load_doc_types_full
from astrolabe.index import build_hash_map, build_index, reindex, update_card
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


class AppState:
    """Holds web server state: config, merged index, storages, doc_types."""

    def __init__(
        self,
        config: AppConfig,
        config_path: Path,
        index: IndexData,
        storage: StorageBackend,
        private_storage: StorageBackend | None,
        doc_types_full: dict[str, dict[str, Any]],
    ) -> None:
        self.config = config
        self.config_path = config_path
        self.index = index
        self.storage = storage
        self.private_storage = private_storage
        self.doc_types_full = doc_types_full
        self.doc_types: dict[str, str] = {
            name: entry["description"] for name, entry in doc_types_full.items()
        }

    @classmethod
    def from_config_path(cls, config_path: Path) -> "AppState":
        """Initialize state from config file path."""
        config = load_config(config_path)

        # Load doc_types
        index_types = config.index_dir / "doc_types.yaml"
        config_types = config_path.parent / "doc_types.yaml"
        if index_types.exists():
            doc_types_full = load_doc_types_full(index_types)
        elif config_types.exists():
            doc_types_full = load_doc_types_full(config_types)
        else:
            doc_types_full = {}

        # Create storages
        storage = create_storage(config)
        private_storage: StorageBackend | None = None
        if config.private_index_dir is not None:
            private_storage = create_storage_at(config.private_index_dir, config.storage)

        # Load and merge indexes
        shared_data = storage.load()
        private_data = private_storage.load() if private_storage is not None else None

        existing_docs: dict[str, Any] = {}
        indexed_at = datetime.now(UTC)
        if shared_data is not None:
            existing_docs.update(shared_data.documents)
            indexed_at = shared_data.indexed_at
        if private_data is not None:
            existing_docs.update(private_data.documents)

        scan_config = _full_scan_config(config)
        if existing_docs:
            existing = IndexData(indexed_at=indexed_at, documents=existing_docs)
            index, stats = reindex(scan_config, existing)
            logger.info("Reindex on startup: %s", stats)
        else:
            index = build_index(scan_config)
            logger.info("Built fresh index: %d documents", len(index.documents))

        state = cls(
            config=config,
            config_path=config_path,
            index=index,
            storage=storage,
            private_storage=private_storage,
            doc_types_full=doc_types_full,
        )
        state._save_index()
        return state

    @classmethod
    def create(cls) -> "AppState":
        """Create state from ASTROLABE_CONFIG env var (or default)."""
        config_path_str = os.environ.get("ASTROLABE_CONFIG", "runtime/config.json")
        config_path = Path(config_path_str).resolve()
        return cls.from_config_path(config_path)

    def reload(self) -> None:
        """Reload index from storage to pick up MCP server changes."""
        shared_data = self.storage.load()
        private_data = self.private_storage.load() if self.private_storage is not None else None

        docs: dict[str, Any] = {}
        indexed_at = datetime.now(UTC)
        if shared_data is not None:
            docs.update(shared_data.documents)
            indexed_at = shared_data.indexed_at
        if private_data is not None:
            docs.update(private_data.documents)

        if docs:
            self.index = IndexData(indexed_at=indexed_at, documents=docs)
        else:
            self.index = build_index(_full_scan_config(self.config))

        logger.info("Reloaded index: %d documents", len(self.index.documents))

    def _save_index(self) -> None:
        """Split index into shared/private and save to corresponding storages."""
        if self.private_storage is None:
            self.storage.save(self.index)
            return

        shared_docs = {}
        private_docs = {}
        for doc_id, card in self.index.documents.items():
            if self.config.is_private(card.project):
                private_docs[doc_id] = card
            else:
                shared_docs[doc_id] = card

        self.storage.save(IndexData(indexed_at=self.index.indexed_at, documents=shared_docs))
        self.private_storage.save(
            IndexData(indexed_at=self.index.indexed_at, documents=private_docs)
        )

    def _get_storage_for_project(self, project: str) -> StorageBackend:
        """Return the correct storage backend for a project."""
        if self.private_storage is not None and self.config.is_private(project):
            return self.private_storage
        return self.storage

    def is_desync(self, card: DocCard) -> bool:
        """Check if card's file is missing on disk."""
        if card.project not in self.config.all_projects:
            return False
        file_path = self.config.all_projects[card.project] / card.rel_path
        return not file_path.exists()

    def save_card(self, card: DocCard) -> None:
        """Persist a single card to the correct storage."""
        storage = self._get_storage_for_project(card.project)
        storage.save_card(card, self.index.indexed_at)

    def do_update_card(
        self,
        doc_id: str,
        *,
        type: str | None = None,
        summary: str | None = None,
        keywords: list[str] | None = None,
        headings: list[str] | None = None,
    ) -> DocCard:
        """Update card enrichment and persist."""
        card = update_card(
            self.index, doc_id, type=type, summary=summary, keywords=keywords, headings=headings
        )
        self.save_card(card)
        return card

    def do_reindex(
        self,
        project: str | None = None,
        mode: str = "update",
    ) -> dict[str, Any]:
        """Run reindex and return stats dict."""
        reindex_mode = cast(Literal["update", "clean", "rebuild"], mode)
        config = self.config
        start = datetime.now(UTC)

        if project is not None:
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
            other_cards = {
                doc_id: card
                for doc_id, card in self.index.documents.items()
                if card.project != project
            }
            project_index = IndexData(
                indexed_at=self.index.indexed_at,
                documents={
                    doc_id: card
                    for doc_id, card in self.index.documents.items()
                    if card.project == project
                },
            )
            new_index, stats = reindex(single_config, project_index, mode=reindex_mode)
            merged = {**other_cards, **new_index.documents}
            self.index = IndexData(indexed_at=new_index.indexed_at, documents=merged)
        else:
            self.index, stats = reindex(_full_scan_config(config), self.index, mode=reindex_mode)

        self._save_index()
        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)

        result: dict[str, Any] = {
            "scanned": stats.scanned,
            "new": stats.new,
            "removed": stats.removed,
            "stale": stats.stale,
            "unchanged": stats.unchanged,
            "passthrough": stats.passthrough,
            "desync": stats.desync,
            "duration_ms": duration_ms,
        }
        if stats.new_divergences:
            result["new_divergences"] = stats.new_divergences
        return result

    def get_cosmos(self) -> CosmosResponse:
        """Build cosmos overview response."""
        from astrolabe import __version__

        config = self.config
        index = self.index

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
        desync_count = 0
        diverged_count = 0
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
                if self.is_desync(card):
                    desync_count += 1
                    project_stats[card.project]["desync_count"] += 1
                if is_diverged:
                    project_stats[card.project]["diverged_count"] += 1

            if is_diverged:
                diverged_count += 1

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
                doc_count=s["doc_count"],
                enriched_count=s["enriched_count"],
                stale_count=s["stale_count"],
                empty_count=s["empty_count"],
                desync_count=s["desync_count"],
                diverged_count=s["diverged_count"],
                last_indexed=index.indexed_at,
            )
            for pid, s in project_stats.items()
        ]

        document_types = [
            TypeSummary(type=t, description=self.doc_types.get(t, ""), count=c)
            for t, c in sorted(type_counts.items())
        ]

        return CosmosResponse(
            server_version=__version__,
            indexed_at=index.indexed_at,
            total_documents=total,
            enriched_documents=enriched,
            stale_documents=stale,
            empty_documents=empty,
            desync_documents=desync_count,
            diverged_documents=diverged_count,
            projects=projects,
            document_types=document_types,
        )

    def list_cards(
        self,
        *,
        project: str | None = None,
        type: str | None = None,
        stale: bool = False,
        desync: bool = False,
        empty: bool = False,
        diverged: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DocCard], int]:
        """Filter and paginate cards. Returns (page, total)."""
        filtered: list[DocCard] = []
        for card in self.index.documents.values():
            if project is not None and card.project != project:
                continue
            if type is not None and card.type != type:
                continue
            if stale and not card.is_stale:
                continue
            if empty and not card.is_empty:
                continue
            if desync and not self.is_desync(card):
                continue
            if diverged and not card.diverged_from:
                continue
            filtered.append(card)

        total = len(filtered)
        page = filtered[offset : offset + limit]
        return page, total

    def accept_divergence(self, doc_id: str) -> dict[str, Any]:
        """Clear diverged_from on a card and persist. Returns status dict."""
        if doc_id not in self.index.documents:
            return {"error": f"Document not found: {doc_id}"}
        card = self.index.documents[doc_id]
        if not card.diverged_from:
            return {"error": "No divergence to accept."}
        cleared = list(card.diverged_from)
        card.diverged_from = None
        self.save_card(card)
        return {"ok": True, "doc_id": doc_id, "cleared_from": cleared}

    def _dedup_results(self, results: list[Any]) -> list[Any]:
        """Deduplicate search results by content_hash."""
        hash_map = build_hash_map(self.index.documents)
        if not hash_map:
            return results
        seen: set[str] = set()
        deduped = []
        for r in results:
            card = self.index.documents.get(r.doc_id)
            if card and card.content_hash in hash_map:
                if card.content_hash in seen:
                    continue
                seen.add(card.content_hash)
            deduped.append(r)
        return deduped

    def search_cards(
        self,
        query: str,
        *,
        project: str | None = None,
        type: str | None = None,
        max_results: int = 20,
    ) -> list[Any]:
        """Search cards by query (fast keyword matching). Returns SearchResult list."""
        type_boosts = {
            name: entry.get("search_boost", 1.0)
            for name, entry in self.doc_types_full.items()
            if "search_boost" in entry
        }
        results = search(
            self.index.documents.values(),
            query,
            project=project,
            type=type,
            type_boosts=type_boosts,
        )
        results = self._dedup_results(results)
        return results[:max_results]

    def read_document(
        self,
        doc_id: str,
        *,
        section: str | None = None,
        line_range: str | None = None,
    ) -> dict[str, Any]:
        """Read document content. Returns dict with content, lines info."""
        if doc_id not in self.index.documents:
            return {"error": f"Document not found: {doc_id}"}

        card = self.index.documents[doc_id]
        project_path = self.config.all_projects.get(card.project)
        if project_path is None:
            return {"error": f"Project not found in config: {card.project}"}

        file_path = project_path / card.rel_path
        if not file_path.exists():
            return {"error": f"File not found: {card.rel_path}"}

        try:
            result = read_file(
                file_path,
                max_size_kb=self.config.max_file_size_kb,
                section=section,
                line_range=line_range,
            )
        except ValueError as e:
            return {"error": str(e)}

        return {
            "content": result.content,
            "total_lines": result.total_lines,
            "returned_lines": result.returned_lines,
            "section": result.section,
            "truncated": result.truncated,
            "available_sections": result.available_sections,
        }


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
