"""Storage abstraction for astrolabe index."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from astrolabe.models import AppConfig, DocCard, IndexData

logger = logging.getLogger(__name__)


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for index storage backends."""

    def load(self) -> IndexData | None:
        """Load entire index from storage.

        Returns None if storage does not exist or is corrupt.
        """
        ...

    def save(self, index: IndexData) -> None:
        """Save entire index (full overwrite)."""
        ...

    def save_card(self, card: DocCard, indexed_at: datetime) -> None:
        """Persist a single card (upsert).

        For JsonStorage: rewrites entire file.
        For SqliteStorage: single INSERT OR REPLACE.

        Args:
            card: The card to persist.
            indexed_at: Current index timestamp for metadata.
        """
        ...

    def exists(self) -> bool:
        """Check if storage file exists on disk."""
        ...

    @property
    def path(self) -> Path:
        """Path to the storage file."""
        ...


def create_storage_at(index_dir: Path, storage_type: str) -> StorageBackend:
    """Create storage backend for a specific directory.

    Core factory used by the server for both shared and private storages.

    Args:
        index_dir: Directory for index files.
        storage_type: "json" or "sqlite".

    Returns:
        JsonStorage or SqliteStorage instance.

    Migration:
        If storage_type is "sqlite" and the .db file does not exist
        but the .json file does, auto-migrates JSON -> SQLite.
    """
    index_dir.mkdir(parents=True, exist_ok=True)
    json_path = index_dir / ".doc-index.json"
    db_path = index_dir / ".doc-index.db"

    if storage_type == "json":
        from astrolabe.storage_json import JsonStorage

        return JsonStorage(json_path)

    from astrolabe.storage_sqlite import SqliteStorage

    # Auto-migrate if JSON exists but SQLite does not
    if not db_path.exists() and json_path.exists():
        from astrolabe.index import load_index

        logger.info("Migrating index from JSON to SQLite...")
        json_index = load_index(json_path)
        if json_index is not None:
            storage = SqliteStorage(db_path)
            storage.save(json_index)
            logger.info(
                "Migrated %d cards from JSON to SQLite: %s",
                len(json_index.documents),
                db_path,
            )
            return storage
        logger.warning("JSON index is corrupt or empty, creating fresh SQLite storage")

    return SqliteStorage(db_path)


def create_storage(config: AppConfig) -> StorageBackend:
    """Create shared storage backend based on config.

    Convenience wrapper. Delegates to create_storage_at(config.index_dir, config.storage).

    Args:
        config: Application config with storage and index_dir fields.

    Returns:
        JsonStorage or SqliteStorage instance.
    """
    return create_storage_at(config.index_dir, config.storage)
