"""Data models for astrolabe-mcp."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from astrolabe import __version__


class AppConfig(BaseModel):
    """Application configuration loaded from config.json."""

    projects: dict[str, Path]
    index_path: Path
    index_extensions: list[str]
    ignore_dirs: list[str]
    ignore_files: list[str]
    max_file_size_kb: int


class DocCard(BaseModel):
    """Single document in the index."""

    project: str
    filename: str
    rel_path: str
    size: int
    modified: datetime
    content_hash: str

    # Enrichment fields (null until agent fills them)
    type: str | None = None
    headings: list[str] | None = None
    summary: str | None = None
    keywords: list[str] | None = None
    enriched_at: datetime | None = None

    @property
    def doc_id(self) -> str:
        """Unique document identifier: project::rel_path."""
        return f"{self.project}::{self.rel_path}"

    @property
    def is_stale(self) -> bool:
        """True if file was modified after last enrichment."""
        return self.enriched_at is not None and self.modified > self.enriched_at

    @property
    def is_empty(self) -> bool:
        """True if card was never enriched."""
        return self.enriched_at is None


class IndexData(BaseModel):
    """Top-level index structure stored in .doc-index.json."""

    version: str = __version__
    indexed_at: datetime
    documents: dict[str, DocCard] = {}


class ProjectSummary(BaseModel):
    """Per-project stats for get_cosmos() response."""

    id: str
    doc_count: int
    enriched_count: int
    last_indexed: datetime


class TypeSummary(BaseModel):
    """Per-type stats for get_cosmos() response."""

    type: str
    description: str
    count: int


class CosmosResponse(BaseModel):
    """Response for get_cosmos() tool."""

    server_version: str
    indexed_at: datetime
    total_documents: int
    enriched_documents: int
    stale_documents: int
    empty_documents: int
    desync_documents: int = 0
    projects: list[ProjectSummary]
    document_types: list[TypeSummary]


class SearchResult(BaseModel):
    """Single result from search_docs()."""

    doc_id: str
    project: str
    type: str | None
    filename: str
    summary: str | None
    keywords: list[str] | None
    relevance: float
