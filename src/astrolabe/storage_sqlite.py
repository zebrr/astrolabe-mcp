"""SQLite storage backend for astrolabe index."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from astrolabe.models import DocCard, IndexData

logger = logging.getLogger(__name__)

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    project      TEXT NOT NULL,
    filename     TEXT NOT NULL,
    rel_path     TEXT NOT NULL,
    size         INTEGER NOT NULL,
    modified     TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    type         TEXT,
    headings     TEXT,
    summary      TEXT,
    keywords     TEXT,
    enriched_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_project ON documents(project);
CREATE INDEX IF NOT EXISTS idx_type ON documents(type);
"""


def _card_to_row(card: DocCard) -> tuple[object, ...]:
    """Convert DocCard to a tuple for INSERT."""
    return (
        card.doc_id,
        card.project,
        card.filename,
        card.rel_path,
        card.size,
        card.modified.isoformat(),
        card.content_hash,
        card.type,
        json.dumps(card.headings) if card.headings is not None else None,
        card.summary,
        json.dumps(card.keywords) if card.keywords is not None else None,
        card.enriched_at.isoformat() if card.enriched_at is not None else None,
    )


def _row_to_card(row: sqlite3.Row) -> DocCard:
    """Convert a database row to DocCard."""
    headings_raw = row["headings"]
    keywords_raw = row["keywords"]
    enriched_raw = row["enriched_at"]

    return DocCard(
        project=row["project"],
        filename=row["filename"],
        rel_path=row["rel_path"],
        size=row["size"],
        modified=datetime.fromisoformat(row["modified"]),
        content_hash=row["content_hash"],
        type=row["type"],
        headings=json.loads(headings_raw) if headings_raw is not None else None,
        summary=row["summary"],
        keywords=json.loads(keywords_raw) if keywords_raw is not None else None,
        enriched_at=datetime.fromisoformat(enriched_raw) if enriched_raw is not None else None,
    )


_INSERT_SQL = """\
INSERT OR REPLACE INTO documents
    (doc_id, project, filename, rel_path, size, modified,
     content_hash, type, headings, summary, keywords, enriched_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SqliteStorage:
    """SQLite storage backend.

    Uses journal_mode=DELETE for cloud drive compatibility.
    Stores headings and keywords as JSON-encoded strings.
    """

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=DELETE")
        self._conn.executescript(_SCHEMA)

    def load(self) -> IndexData | None:
        """Load entire index from SQLite database."""
        try:
            # Read metadata
            cursor = self._conn.execute("SELECT key, value FROM meta")
            meta = dict(cursor.fetchall())

            if "indexed_at" not in meta:
                return None

            version = meta.get("version", "")
            indexed_at = datetime.fromisoformat(meta["indexed_at"])

            # Read all documents
            cursor = self._conn.execute("SELECT * FROM documents")
            documents: dict[str, DocCard] = {}
            for row in cursor:
                card = _row_to_card(row)
                documents[card.doc_id] = card

            return IndexData(
                version=version,
                indexed_at=indexed_at,
                documents=documents,
            )
        except (sqlite3.Error, KeyError, ValueError) as e:
            logger.warning("Failed to load SQLite index: %s", e)
            return None

    def save(self, index: IndexData) -> None:
        """Save entire index (full overwrite) in a single transaction."""
        with self._conn:
            self._conn.execute("DELETE FROM documents")
            self._conn.execute("DELETE FROM meta")

            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                ("version", index.version),
            )
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                ("indexed_at", index.indexed_at.isoformat()),
            )

            self._conn.executemany(
                _INSERT_SQL,
                [_card_to_row(card) for card in index.documents.values()],
            )

    def save_card(self, card: DocCard, indexed_at: datetime) -> None:
        """Persist a single card via INSERT OR REPLACE."""
        with self._conn:
            self._conn.execute(_INSERT_SQL, _card_to_row(card))
            self._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("indexed_at", indexed_at.isoformat()),
            )

    def exists(self) -> bool:
        """Check if database file exists."""
        return self._path.exists()

    @property
    def path(self) -> Path:
        """Path to the SQLite database file."""
        return self._path

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
