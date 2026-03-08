"""JSON file storage backend for astrolabe index."""

from datetime import datetime
from pathlib import Path

from astrolabe.index import load_index, save_index
from astrolabe.models import DocCard, IndexData


class JsonStorage:
    """JSON file storage backend.

    Delegates to load_index/save_index in index.py.
    Same behavior as pre-abstraction code.
    """

    def __init__(self, index_path: Path) -> None:
        self._path = index_path

    def load(self) -> IndexData | None:
        """Load index from JSON file."""
        return load_index(self._path)

    def save(self, index: IndexData) -> None:
        """Save entire index to JSON file."""
        save_index(index, self._path)

    def save_card(self, card: DocCard, indexed_at: datetime) -> None:
        """Save a single card by rewriting the entire JSON file."""
        index = load_index(self._path)
        if index is None:
            index = IndexData(indexed_at=indexed_at, documents={})
        index.documents[card.doc_id] = card
        index.indexed_at = indexed_at
        save_index(index, self._path)

    def exists(self) -> bool:
        """Check if JSON file exists."""
        return self._path.exists()

    @property
    def path(self) -> Path:
        """Path to the JSON file."""
        return self._path
