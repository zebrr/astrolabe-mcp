"""Core index module: scan, build, load, save, reindex, update."""

import contextlib
import hashlib
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Literal

from filelock import FileLock

from astrolabe.models import AppConfig, DocCard, IndexData

logger = logging.getLogger(__name__)


@dataclass
class ReindexStats:
    """Statistics from a reindex operation."""

    scanned: int = 0
    new: int = 0
    removed: int = 0
    stale: int = 0
    unchanged: int = 0
    passthrough: int = 0
    desync: int = 0
    auto_transferred: list[tuple[str, str]] = field(default_factory=list)
    ambiguous_moves: list[dict[str, object]] = field(default_factory=list)


def _compute_hash(file_path: Path) -> str:
    """Compute MD5 hex digest of file contents.

    Normalizes CRLF to LF before hashing for cross-platform consistency.
    """
    raw = file_path.read_bytes()
    raw = raw.replace(b"\r\n", b"\n")
    return hashlib.md5(raw).hexdigest()


def _matches_ignore_files(filename: str, patterns: list[str]) -> bool:
    """Check if filename matches any glob pattern from ignore_files."""
    return any(fnmatch(filename, pat) for pat in patterns)


def _list_files_git(project_path: Path) -> list[Path] | None:
    """List files via git ls-files. Returns None if not a git repo or git unavailable."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        logger.info("git not found, falling back to rglob for %s", project_path)
        return None
    except subprocess.TimeoutExpired:
        logger.warning("git ls-files timed out for %s, falling back to rglob", project_path)
        return None

    if result.returncode != 0:
        logger.info("Not a git repo: %s, falling back to rglob", project_path)
        return None

    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    return [project_path / line for line in lines]


def _list_files_rglob(project_path: Path) -> list[Path]:
    """List files via rglob (fallback for non-git directories)."""
    return [p for p in project_path.rglob("*") if p.is_file() and not p.is_symlink()]


def scan_project(project_id: str, project_path: Path, config: AppConfig) -> list[DocCard]:
    """Discover files in a project and create DocCards for matching files.

    Uses git ls-files as primary source; falls back to rglob for non-git directories.
    Astrolabe filters (ignore_dirs, ignore_files, index_extensions) apply on top.
    """
    cards: list[DocCard] = []

    if not project_path.is_dir():
        logger.warning("Project path does not exist: %s", project_path)
        return cards

    # Two-tier file discovery: git-aware primary, rglob fallback
    file_paths = _list_files_git(project_path)
    if file_paths is None:
        file_paths = _list_files_rglob(project_path)

    for file_path in file_paths:
        if not file_path.is_file() or file_path.is_symlink():
            continue

        # Check ignore_dirs: skip if any path component matches
        rel = file_path.relative_to(project_path)
        if any(part in config.ignore_dirs for part in rel.parts[:-1]):
            continue

        # Check extension
        if file_path.suffix not in config.index_extensions:
            continue

        # Check ignore_files
        if _matches_ignore_files(file_path.name, config.ignore_files):
            continue

        try:
            stat = file_path.stat()
            content_hash = _compute_hash(file_path)
        except OSError:
            logger.warning("Cannot read file: %s", file_path)
            continue

        card = DocCard(
            project=project_id,
            filename=file_path.name,
            rel_path=rel.as_posix(),
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            content_hash=content_hash,
        )
        cards.append(card)

    return cards


def load_index(index_path: Path) -> IndexData | None:
    """Load existing index from disk. Returns None if missing or corrupt."""
    if not index_path.exists():
        return None

    lock = FileLock(str(index_path) + ".lock")
    try:
        with lock:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            return IndexData.model_validate(raw)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Corrupt index file, backing up: %s", e)
        backup = index_path.with_suffix(".json.bak")
        with contextlib.suppress(OSError):
            index_path.rename(backup)
        return None


def save_index(index: IndexData, index_path: Path) -> None:
    """Save index to disk atomically with file locking."""
    lock = FileLock(str(index_path) + ".lock")
    data = index.model_dump(mode="json")

    with lock:
        # Write to temp file, then rename for atomicity
        fd, tmp_path = tempfile.mkstemp(dir=index_path.parent, suffix=".tmp", prefix=".doc-index-")
        try:
            tmp = Path(tmp_path)
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(index_path)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        finally:
            with contextlib.suppress(OSError):
                os.close(fd)


def build_index(config: AppConfig) -> IndexData:
    """Full index build from scratch."""
    documents: dict[str, DocCard] = {}

    for project_id, project_path in config.projects.items():
        cards = scan_project(project_id, project_path, config)
        for card in cards:
            documents[card.doc_id] = card

    return IndexData(
        indexed_at=datetime.now(UTC),
        documents=documents,
    )


def reindex(
    config: AppConfig,
    existing: IndexData | None = None,
    *,
    mode: Literal["update", "clean", "rebuild"] = "update",
) -> tuple[IndexData, ReindexStats]:
    """Rescan filesystem and merge with existing index.

    Modes (escalating):
    - update: preserve desync cards, preserve enrichment, detect moves
    - clean: remove desync cards, preserve enrichment, skip move detection
    - rebuild: remove desync cards, reset enrichment, skip move detection

    Pass-through cards (foreign projects) are always preserved.
    """
    stats = ReindexStats()

    # Scan all projects
    fresh_cards: dict[str, DocCard] = {}
    for project_id, project_path in config.projects.items():
        for card in scan_project(project_id, project_path, config):
            fresh_cards[card.doc_id] = card
            stats.scanned += 1

    if existing is None:
        stats.new = len(fresh_cards)
        return IndexData(indexed_at=datetime.now(UTC), documents=fresh_cards), stats

    new_documents: dict[str, DocCard] = {}

    # Process fresh cards against existing
    for doc_id, fresh_card in fresh_cards.items():
        if doc_id not in existing.documents:
            new_documents[doc_id] = fresh_card
            stats.new += 1
        elif mode == "rebuild":
            # Rebuild: use fresh card without enrichment
            new_documents[doc_id] = fresh_card
            stats.new += 1
        else:
            old_card = existing.documents[doc_id]
            if old_card.content_hash != fresh_card.content_hash:
                # File changed: update metadata, preserve enrichment
                fresh_card.type = old_card.type
                fresh_card.headings = old_card.headings
                fresh_card.summary = old_card.summary
                fresh_card.keywords = old_card.keywords
                fresh_card.enriched_at = old_card.enriched_at
                fresh_card.enriched_content_hash = old_card.enriched_content_hash
                new_documents[doc_id] = fresh_card
                stats.stale += 1
            else:
                # Unchanged — migrate enriched cards missing enriched_content_hash
                if old_card.enriched_at is not None and old_card.enriched_content_hash is None:
                    old_card.enriched_content_hash = old_card.content_hash
                new_documents[doc_id] = old_card
                stats.unchanged += 1

    # Cards not in fresh scan
    for doc_id, card in existing.documents.items():
        if doc_id in fresh_cards:
            continue
        if card.project not in config.projects:
            # Pass-through: foreign project, preserve as-is
            new_documents[doc_id] = card
            stats.passthrough += 1
        elif mode in ("clean", "rebuild"):
            # Clean/rebuild: remove desync cards for configured projects
            stats.removed += 1
        else:
            # Desync: file missing but project is configured, preserve card
            new_documents[doc_id] = card
            stats.desync += 1

    # Detect moves by content_hash: enriched desync → new empty cards
    if mode == "update":
        desync_by_hash: dict[str, list[str]] = {}
        for doc_id, card in existing.documents.items():
            if (
                doc_id not in fresh_cards
                and card.project in config.projects
                and card.enriched_at is not None
            ):
                desync_by_hash.setdefault(card.content_hash, []).append(doc_id)

        new_by_hash: dict[str, list[str]] = {}
        for doc_id in fresh_cards:
            merged = new_documents.get(doc_id)
            if merged and merged.is_empty:
                new_by_hash.setdefault(merged.content_hash, []).append(doc_id)

        for content_hash, desync_ids in desync_by_hash.items():
            new_ids = new_by_hash.get(content_hash)
            if not new_ids:
                continue
            if len(desync_ids) == 1 and len(new_ids) == 1:
                old_id, new_id = desync_ids[0], new_ids[0]
                old_card = new_documents[old_id]
                new_card = new_documents[new_id]
                # Transfer enrichment
                new_card.type = old_card.type
                new_card.summary = old_card.summary
                new_card.keywords = old_card.keywords
                new_card.headings = old_card.headings
                new_card.enriched_at = old_card.enriched_at
                new_card.enriched_content_hash = new_card.content_hash
                # Remove desync card from index
                del new_documents[old_id]
                stats.desync -= 1
                stats.auto_transferred.append((old_id, new_id))
            else:
                stats.ambiguous_moves.append(
                    {
                        "hash": content_hash,
                        "desync_ids": desync_ids,
                        "new_ids": new_ids,
                    }
                )

    return IndexData(indexed_at=datetime.now(UTC), documents=new_documents), stats


def update_card(
    index: IndexData,
    doc_id: str,
    *,
    type: str | None = None,
    summary: str | None = None,
    keywords: list[str] | None = None,
    headings: list[str] | None = None,
) -> DocCard:
    """Update enrichment fields on a card.

    Only updates fields that are explicitly passed (not None).
    Raises KeyError if doc_id not in index.
    """
    if doc_id not in index.documents:
        raise KeyError(f"Document not found: {doc_id}")

    card = index.documents[doc_id]
    if type is not None:
        card.type = type
    if summary is not None:
        card.summary = summary
    if keywords is not None:
        card.keywords = keywords
    if headings is not None:
        card.headings = headings
    card.enriched_at = datetime.now(UTC)
    card.enriched_content_hash = card.content_hash
    return card
