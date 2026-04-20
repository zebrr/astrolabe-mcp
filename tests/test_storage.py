"""Tests for storage backends (JsonStorage and SqliteStorage)."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from astrolabe.models import AppConfig, DocCard, IndexData
from astrolabe.storage import StorageBackend, create_storage, create_storage_at
from astrolabe.storage_json import JsonStorage
from astrolabe.storage_sqlite import SqliteStorage


def _make_card(
    project: str = "proj",
    rel_path: str = "docs/readme.md",
    *,
    enriched: bool = False,
) -> DocCard:
    """Create a test DocCard."""
    card = DocCard(
        project=project,
        filename=Path(rel_path).name,
        rel_path=rel_path,
        size=100,
        modified=datetime(2026, 1, 1, tzinfo=UTC),
        content_hash="abc123",
    )
    if enriched:
        card.type = "reference"
        card.summary = "A readme file."
        card.keywords = ["readme", "docs"]
        card.headings = ["Introduction", "Usage"]
        card.enriched_at = datetime(2026, 1, 2, tzinfo=UTC)
        card.enriched_content_hash = card.content_hash
    return card


def _make_index(cards: list[DocCard] | None = None) -> IndexData:
    """Create a test IndexData."""
    if cards is None:
        cards = [_make_card()]
    return IndexData(
        indexed_at=datetime(2026, 1, 1, tzinfo=UTC),
        documents={c.doc_id: c for c in cards},
    )


@pytest.fixture(params=["json", "sqlite"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> StorageBackend:
    """Parametrized fixture: returns both JsonStorage and SqliteStorage."""
    if request.param == "json":
        return JsonStorage(tmp_path / ".doc-index.json")
    return SqliteStorage(tmp_path / ".doc-index.db")


class TestProtocolCompliance:
    """Both backends satisfy the StorageBackend protocol."""

    def test_json_is_storage_backend(self, tmp_path: Path) -> None:
        s = JsonStorage(tmp_path / "index.json")
        assert isinstance(s, StorageBackend)

    def test_sqlite_is_storage_backend(self, tmp_path: Path) -> None:
        s = SqliteStorage(tmp_path / "index.db")
        assert isinstance(s, StorageBackend)


class TestLoadSaveRoundtrip:
    """load/save roundtrip preserves all data."""

    def test_empty_load_returns_none(self, storage: StorageBackend) -> None:
        # SQLite creates the file on __init__, but has no meta rows
        result = storage.load()
        assert result is None

    def test_save_and_load(self, storage: StorageBackend) -> None:
        index = _make_index()
        storage.save(index)
        loaded = storage.load()

        assert loaded is not None
        assert len(loaded.documents) == 1
        card = list(loaded.documents.values())[0]
        assert card.project == "proj"
        assert card.rel_path == "docs/readme.md"
        assert card.content_hash == "abc123"

    def test_enriched_card_roundtrip(self, storage: StorageBackend) -> None:
        card = _make_card(enriched=True)
        index = _make_index([card])
        storage.save(index)
        loaded = storage.load()

        assert loaded is not None
        loaded_card = loaded.documents[card.doc_id]
        assert loaded_card.type == "reference"
        assert loaded_card.summary == "A readme file."
        assert loaded_card.keywords == ["readme", "docs"]
        assert loaded_card.headings == ["Introduction", "Usage"]
        assert loaded_card.enriched_at == datetime(2026, 1, 2, tzinfo=UTC)
        assert loaded_card.enriched_content_hash == "abc123"

    def test_stale_card_roundtrip(self, storage: StorageBackend) -> None:
        """Stale card (content changed after enrichment) survives roundtrip."""
        card = _make_card(enriched=True)
        card.content_hash = "new_hash"  # simulate file change
        assert card.is_stale

        storage.save(_make_index([card]))
        loaded = storage.load()
        assert loaded is not None
        loaded_card = list(loaded.documents.values())[0]
        assert loaded_card.content_hash == "new_hash"
        assert loaded_card.enriched_content_hash == "abc123"
        assert loaded_card.is_stale

    def test_multiple_cards(self, storage: StorageBackend) -> None:
        cards = [
            _make_card("proj1", "a.md"),
            _make_card("proj2", "b.md", enriched=True),
            _make_card("proj1", "sub/c.md"),
        ]
        index = _make_index(cards)
        storage.save(index)
        loaded = storage.load()

        assert loaded is not None
        assert len(loaded.documents) == 3
        assert "proj1::a.md" in loaded.documents
        assert "proj2::b.md" in loaded.documents
        assert "proj1::sub/c.md" in loaded.documents

    def test_save_overwrites(self, storage: StorageBackend) -> None:
        """Second save replaces all data."""
        index1 = _make_index([_make_card("proj", "a.md")])
        storage.save(index1)

        index2 = _make_index([_make_card("proj", "b.md")])
        storage.save(index2)

        loaded = storage.load()
        assert loaded is not None
        assert len(loaded.documents) == 1
        assert "proj::b.md" in loaded.documents

    def test_indexed_at_preserved(self, storage: StorageBackend) -> None:
        ts = datetime(2026, 6, 15, 12, 30, tzinfo=UTC)
        index = IndexData(indexed_at=ts, documents={})
        storage.save(index)
        loaded = storage.load()
        assert loaded is not None
        assert loaded.indexed_at == ts


class TestSaveCard:
    """save_card persists a single card."""

    def test_save_card_to_existing_index(self, storage: StorageBackend) -> None:
        index = _make_index([_make_card("proj", "a.md")])
        storage.save(index)

        new_card = _make_card("proj", "b.md", enriched=True)
        storage.save_card(new_card, index.indexed_at)

        loaded = storage.load()
        assert loaded is not None
        assert len(loaded.documents) == 2
        assert "proj::b.md" in loaded.documents
        assert loaded.documents["proj::b.md"].type == "reference"

    def test_save_card_updates_existing(self, storage: StorageBackend) -> None:
        card = _make_card("proj", "a.md")
        index = _make_index([card])
        storage.save(index)

        # Enrich the same card
        card.type = "spec"
        card.summary = "Updated summary"
        card.enriched_at = datetime(2026, 3, 1, tzinfo=UTC)
        storage.save_card(card, index.indexed_at)

        loaded = storage.load()
        assert loaded is not None
        assert len(loaded.documents) == 1
        loaded_card = loaded.documents["proj::a.md"]
        assert loaded_card.type == "spec"
        assert loaded_card.summary == "Updated summary"

    def test_save_card_to_empty_storage(self, storage: StorageBackend) -> None:
        """save_card works even if storage has no prior data."""
        card = _make_card("proj", "new.md")
        ts = datetime(2026, 1, 1, tzinfo=UTC)

        # For SQLite, this inserts into empty DB
        # For JSON, this creates a new file
        storage.save_card(card, ts)

        loaded = storage.load()
        assert loaded is not None
        assert "proj::new.md" in loaded.documents


class TestExists:
    """exists() checks storage file presence."""

    def test_json_exists_false_before_save(self, tmp_path: Path) -> None:
        s = JsonStorage(tmp_path / "index.json")
        assert s.exists() is False

    def test_json_exists_true_after_save(self, tmp_path: Path) -> None:
        s = JsonStorage(tmp_path / "index.json")
        s.save(_make_index())
        assert s.exists() is True

    def test_sqlite_exists_true_after_init(self, tmp_path: Path) -> None:
        # SQLite creates the file on connect
        s = SqliteStorage(tmp_path / "index.db")
        assert s.exists() is True


class TestPath:
    """path property returns correct path."""

    def test_json_path(self, tmp_path: Path) -> None:
        p = tmp_path / "my-index.json"
        s = JsonStorage(p)
        assert s.path == p

    def test_sqlite_path(self, tmp_path: Path) -> None:
        p = tmp_path / "my-index.db"
        s = SqliteStorage(p)
        assert s.path == p


class TestCreateStorageFactory:
    """create_storage() factory selects correct backend."""

    def _make_config(self, tmp_path: Path, storage: str = "json") -> AppConfig:
        return AppConfig(
            projects={"test": tmp_path / "project"},
            index_dir=tmp_path,
            storage=storage,  # type: ignore[arg-type]
            index_extensions=[".md"],
            ignore_dirs=[".git"],
            ignore_files=[],
            max_file_size_kb=500,
        )

    def test_json_backend(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path, "json")
        s = create_storage(config)
        assert isinstance(s, JsonStorage)

    def test_sqlite_backend(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path, "sqlite")
        s = create_storage(config)
        assert isinstance(s, SqliteStorage)

    def test_sqlite_path_derived_from_index_dir(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path, "sqlite")
        s = create_storage(config)
        assert s.path == tmp_path / ".doc-index.db"

    def test_auto_migration(self, tmp_path: Path) -> None:
        """When switching to sqlite, existing JSON is auto-migrated."""
        # First, save a JSON index
        json_config = self._make_config(tmp_path, "json")
        json_storage = create_storage(json_config)
        card = _make_card(enriched=True)
        index = _make_index([card])
        json_storage.save(index)
        assert (json_config.index_dir / ".doc-index.json").exists()

        # Now switch to sqlite — should auto-migrate
        sqlite_config = self._make_config(tmp_path, "sqlite")
        sqlite_storage = create_storage(sqlite_config)
        assert isinstance(sqlite_storage, SqliteStorage)

        loaded = sqlite_storage.load()
        assert loaded is not None
        assert len(loaded.documents) == 1
        loaded_card = list(loaded.documents.values())[0]
        assert loaded_card.type == "reference"
        assert loaded_card.summary == "A readme file."
        assert loaded_card.keywords == ["readme", "docs"]

        # JSON file still exists (backup)
        assert (json_config.index_dir / ".doc-index.json").exists()

    def test_no_migration_if_sqlite_exists(self, tmp_path: Path) -> None:
        """If SQLite already exists, no migration happens."""
        # Create both JSON and SQLite
        json_config = self._make_config(tmp_path, "json")
        json_s = create_storage(json_config)
        json_s.save(_make_index([_make_card("proj", "from-json.md")]))

        sqlite_config = self._make_config(tmp_path, "sqlite")
        sqlite_s = SqliteStorage(tmp_path / ".doc-index.db")
        sqlite_s.save(_make_index([_make_card("proj", "from-sqlite.md")]))

        # Factory should return existing SQLite, not re-migrate
        result = create_storage(sqlite_config)
        loaded = result.load()
        assert loaded is not None
        assert "proj::from-sqlite.md" in loaded.documents
        assert "proj::from-json.md" not in loaded.documents


class TestCreateStorageAt:
    """create_storage_at() creates correct backends for arbitrary directories."""

    def test_json_at_custom_dir(self, tmp_path: Path) -> None:
        custom = tmp_path / "custom"
        custom.mkdir()
        s = create_storage_at(custom, "json")
        assert isinstance(s, JsonStorage)
        assert s.path == custom / ".doc-index.json"

    def test_sqlite_at_custom_dir(self, tmp_path: Path) -> None:
        custom = tmp_path / "custom"
        custom.mkdir()
        s = create_storage_at(custom, "sqlite")
        assert isinstance(s, SqliteStorage)
        assert s.path == custom / ".doc-index.db"

    def test_two_independent_storages(self, tmp_path: Path) -> None:
        """Two storages in different dirs are independent."""
        dir_a = tmp_path / "shared"
        dir_b = tmp_path / "private"
        dir_a.mkdir()
        dir_b.mkdir()

        s_a = create_storage_at(dir_a, "json")
        s_b = create_storage_at(dir_b, "json")

        card_a = _make_card("proj_a", "a.md")
        card_b = _make_card("proj_b", "b.md")

        s_a.save(_make_index([card_a]))
        s_b.save(_make_index([card_b]))

        loaded_a = s_a.load()
        loaded_b = s_b.load()
        assert loaded_a is not None
        assert loaded_b is not None
        assert "proj_a::a.md" in loaded_a.documents
        assert "proj_b::b.md" in loaded_b.documents
        assert "proj_b::b.md" not in loaded_a.documents


class TestSqliteRetry:
    """Retry logic for transient SQLite errors (cloud drive sync)."""

    def test_retry_write_succeeds_after_transient_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_retry_write retries and succeeds when transient error resolves."""
        import astrolabe.storage_sqlite as mod

        monkeypatch.setattr(mod, "WRITE_RETRY_DELAY_S", 0.0)

        s = SqliteStorage(tmp_path / "index.db")
        call_count = 0

        def flaky_fn() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise sqlite3.OperationalError("attempt to write a readonly database")

        s._retry_write(flaky_fn)
        assert call_count == 3  # failed twice, succeeded on third

    def test_retry_write_raises_after_max_retries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_retry_write raises after exhausting all retries."""
        import astrolabe.storage_sqlite as mod

        monkeypatch.setattr(mod, "WRITE_RETRY_DELAY_S", 0.0)

        s = SqliteStorage(tmp_path / "index.db")

        def always_fail() -> None:
            raise sqlite3.OperationalError("attempt to write a readonly database")

        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            s._retry_write(always_fail)

    def test_retry_write_no_retry_on_non_transient(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-transient OperationalError is raised immediately, no retry."""
        import astrolabe.storage_sqlite as mod

        monkeypatch.setattr(mod, "WRITE_RETRY_DELAY_S", 0.0)

        s = SqliteStorage(tmp_path / "index.db")
        call_count = 0

        def non_transient() -> None:
            nonlocal call_count
            call_count += 1
            raise sqlite3.OperationalError("no such table: documents")

        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            s._retry_write(non_transient)
        assert call_count == 1

    def test_retry_write_handles_locked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'database is locked' is recognized as transient."""
        import astrolabe.storage_sqlite as mod

        monkeypatch.setattr(mod, "WRITE_RETRY_DELAY_S", 0.0)

        s = SqliteStorage(tmp_path / "index.db")
        call_count = 0

        def locked_then_ok() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise sqlite3.OperationalError("database is locked")

        s._retry_write(locked_then_ok)
        assert call_count == 2

    def test_retry_write_handles_busy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'database is busy' is recognized as transient."""
        import astrolabe.storage_sqlite as mod

        monkeypatch.setattr(mod, "WRITE_RETRY_DELAY_S", 0.0)

        s = SqliteStorage(tmp_path / "index.db")
        call_count = 0

        def busy_then_ok() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise sqlite3.OperationalError("database table is busy")

        s._retry_write(busy_then_ok)
        assert call_count == 2

    def test_retry_logs_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Transient errors are logged as warnings during retry."""
        import astrolabe.storage_sqlite as mod

        monkeypatch.setattr(mod, "WRITE_RETRY_DELAY_S", 0.0)

        s = SqliteStorage(tmp_path / "index.db")
        call_count = 0

        def flaky_once() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise sqlite3.OperationalError("attempt to write a readonly database")

        with caplog.at_level("WARNING"):
            s._retry_write(flaky_once)

        assert "Transient SQLite error" in caplog.text
        assert "readonly" in caplog.text

    def test_save_with_readonly_db_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Integration: save() handles OS-level readonly file via retry."""
        import os
        import threading

        import astrolabe.storage_sqlite as mod

        monkeypatch.setattr(mod, "WRITE_RETRY_DELAY_S", 0.3)

        db_path = tmp_path / "index.db"
        s = SqliteStorage(db_path)
        s.save(_make_index([_make_card("proj", "a.md")]))

        # Make file readonly (simulates Google Drive sync)
        os.chmod(db_path, 0o444)

        # Restore permissions after a short delay (simulates sync finishing)
        def restore() -> None:
            import time

            time.sleep(0.15)
            os.chmod(db_path, 0o644)

        t = threading.Thread(target=restore)
        t.start()

        # This should fail on first attempt, succeed after restore
        new_index = _make_index([_make_card("proj", "b.md")])
        s.save(new_index)

        t.join()

        loaded = s.load()
        assert loaded is not None
        assert "proj::b.md" in loaded.documents


class TestSqliteSpecific:
    """SQLite-specific behavior."""

    def test_close(self, tmp_path: Path) -> None:
        s = SqliteStorage(tmp_path / "index.db")
        s.save(_make_index())
        s.close()
        # After close, creating new instance should work
        s2 = SqliteStorage(tmp_path / "index.db")
        loaded = s2.load()
        assert loaded is not None

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "c" / "index.db"
        s = SqliteStorage(deep_path)
        assert deep_path.exists()
        s.save(_make_index())
        loaded = s.load()
        assert loaded is not None

    def test_null_enrichment_fields(self, tmp_path: Path) -> None:
        """Cards with None enrichment fields are stored correctly."""
        card = _make_card()  # not enriched
        assert card.type is None
        assert card.headings is None

        s = SqliteStorage(tmp_path / "index.db")
        s.save(_make_index([card]))
        loaded = s.load()
        assert loaded is not None
        loaded_card = list(loaded.documents.values())[0]
        assert loaded_card.type is None
        assert loaded_card.headings is None
        assert loaded_card.summary is None
        assert loaded_card.keywords is None
        assert loaded_card.enriched_at is None
        assert loaded_card.enriched_content_hash is None

    def test_busy_timeout_set(self, tmp_path: Path) -> None:
        """SQLite connection has busy_timeout for multi-process safety."""
        s = SqliteStorage(tmp_path / "index.db")
        cursor = s._conn.execute("PRAGMA busy_timeout")
        timeout = cursor.fetchone()[0]
        assert timeout >= 3000

    def test_concurrent_read_write(self, tmp_path: Path) -> None:
        """save_card succeeds while another connection holds a brief read lock."""
        import sqlite3
        import threading
        import time

        db_path = tmp_path / "index.db"
        s = SqliteStorage(db_path)
        card = _make_card(enriched=True)
        s.save(_make_index([card]))

        barrier = threading.Barrier(2, timeout=5)

        def reader() -> None:
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA journal_mode=DELETE")
            # Hold SHARED lock briefly (simulates App reading)
            conn.execute("BEGIN")
            conn.execute("SELECT * FROM documents")
            barrier.wait()  # signal: lock is held
            time.sleep(0.1)  # hold for 100ms
            conn.execute("ROLLBACK")
            conn.close()

        t = threading.Thread(target=reader)
        t.start()
        barrier.wait()  # wait until reader holds the lock

        # Write while reader holds SHARED lock — busy_timeout retries until lock is free
        new_card = _make_card("proj", "new.md")
        s.save_card(new_card, datetime(2026, 1, 1, tzinfo=UTC))

        t.join()

        loaded = s.load()
        assert loaded is not None
        assert "proj::new.md" in loaded.documents

    def test_schema_migration_adds_enriched_content_hash(self, tmp_path: Path) -> None:
        """Opening a DB without enriched_content_hash column auto-migrates."""
        import sqlite3 as _sqlite3

        db_path = tmp_path / "legacy.db"
        conn = _sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE documents (
                doc_id TEXT PRIMARY KEY, project TEXT NOT NULL,
                filename TEXT NOT NULL, rel_path TEXT NOT NULL,
                size INTEGER NOT NULL, modified TEXT NOT NULL,
                content_hash TEXT NOT NULL, type TEXT,
                headings TEXT, summary TEXT, keywords TEXT, enriched_at TEXT
            );
        """)
        conn.execute("INSERT INTO meta VALUES ('version', '0.7.0')")
        conn.execute("INSERT INTO meta VALUES ('indexed_at', '2026-01-01T00:00:00+00:00')")
        conn.execute("""
            INSERT INTO documents VALUES (
                'proj::doc.md', 'proj', 'doc.md', 'doc.md', 100,
                '2026-01-01T00:00:00+00:00', 'abc123',
                'spec', NULL, 'A spec', NULL, '2026-01-02T00:00:00+00:00'
            )
        """)
        conn.commit()
        conn.close()

        # Open with SqliteStorage — should auto-migrate
        s = SqliteStorage(db_path)
        loaded = s.load()
        assert loaded is not None
        card = loaded.documents["proj::doc.md"]
        assert card.enriched_content_hash is None  # old row had no value
        assert card.type == "spec"

        # Now save a card with enriched_content_hash
        card.enriched_content_hash = card.content_hash
        s.save_card(card, loaded.indexed_at)

        loaded2 = s.load()
        assert loaded2 is not None
        assert loaded2.documents["proj::doc.md"].enriched_content_hash == "abc123"

    def test_schema_migration_adds_diverged_from(self, tmp_path: Path) -> None:
        """Opening a DB without diverged_from column auto-migrates."""
        import sqlite3 as _sqlite3

        db_path = tmp_path / "legacy_no_diverged.db"
        conn = _sqlite3.connect(str(db_path))
        # Simulate a v0.8/v0.9 DB: has enriched_content_hash, but no diverged_from
        conn.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE documents (
                doc_id TEXT PRIMARY KEY, project TEXT NOT NULL,
                filename TEXT NOT NULL, rel_path TEXT NOT NULL,
                size INTEGER NOT NULL, modified TEXT NOT NULL,
                content_hash TEXT NOT NULL, type TEXT,
                headings TEXT, summary TEXT, keywords TEXT, enriched_at TEXT,
                enriched_content_hash TEXT
            );
        """)
        conn.execute("INSERT INTO meta VALUES ('version', '0.9.2')")
        conn.execute("INSERT INTO meta VALUES ('indexed_at', '2026-01-01T00:00:00+00:00')")
        conn.execute("""
            INSERT INTO documents VALUES (
                'proj::doc.md', 'proj', 'doc.md', 'doc.md', 100,
                '2026-01-01T00:00:00+00:00', 'abc123',
                'spec', NULL, 'A spec', NULL, '2026-01-02T00:00:00+00:00', 'abc123'
            )
        """)
        conn.commit()
        conn.close()

        s = SqliteStorage(db_path)
        loaded = s.load()
        assert loaded is not None
        card = loaded.documents["proj::doc.md"]
        assert card.diverged_from is None  # legacy row

        # Round-trip with divergence set
        card.diverged_from = ["other::doc.md"]
        s.save_card(card, loaded.indexed_at)

        loaded2 = s.load()
        assert loaded2 is not None
        assert loaded2.documents["proj::doc.md"].diverged_from == ["other::doc.md"]

    def test_diverged_from_roundtrip(self, tmp_path: Path) -> None:
        """diverged_from field survives save/load in both SQLite and JSON."""
        s = SqliteStorage(tmp_path / "index.db")
        card = _make_card(enriched=True)
        card.diverged_from = ["other::a.md", "other::b.md"]

        s.save(_make_index([card]))
        loaded = s.load()
        assert loaded is not None
        loaded_card = list(loaded.documents.values())[0]
        assert loaded_card.diverged_from == ["other::a.md", "other::b.md"]

    def test_schema_migration_adds_date(self, tmp_path: Path) -> None:
        """Opening a DB without date column auto-migrates (v0.10.0)."""
        import sqlite3 as _sqlite3

        db_path = tmp_path / "legacy_no_date.db"
        conn = _sqlite3.connect(str(db_path))
        # Simulate a v0.9.x DB: has diverged_from, but no date
        conn.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE documents (
                doc_id TEXT PRIMARY KEY, project TEXT NOT NULL,
                filename TEXT NOT NULL, rel_path TEXT NOT NULL,
                size INTEGER NOT NULL, modified TEXT NOT NULL,
                content_hash TEXT NOT NULL, type TEXT,
                headings TEXT, summary TEXT, keywords TEXT, enriched_at TEXT,
                enriched_content_hash TEXT, diverged_from TEXT
            );
        """)
        conn.execute("INSERT INTO meta VALUES ('version', '0.9.3')")
        conn.execute("INSERT INTO meta VALUES ('indexed_at', '2026-01-01T00:00:00+00:00')")
        conn.execute("""
            INSERT INTO documents VALUES (
                'proj::doc.md', 'proj', 'doc.md', 'doc.md', 100,
                '2026-01-01T00:00:00+00:00', 'abc123',
                'spec', NULL, 'A spec', NULL,
                '2026-01-02T00:00:00+00:00', 'abc123', NULL
            )
        """)
        conn.commit()
        conn.close()

        # Open with new SqliteStorage — should auto-migrate
        s = SqliteStorage(db_path)
        loaded = s.load()
        assert loaded is not None
        card = loaded.documents["proj::doc.md"]
        assert card.date is None  # legacy row
        assert card.type == "spec"

        # Round-trip with date set
        card.date = "2025-11-30"
        s.save_card(card, loaded.indexed_at)

        loaded2 = s.load()
        assert loaded2 is not None
        assert loaded2.documents["proj::doc.md"].date == "2025-11-30"

    def test_date_roundtrip(self, tmp_path: Path) -> None:
        """date field survives save/load in SQLite."""
        s = SqliteStorage(tmp_path / "index.db")
        card = _make_card(enriched=True)
        card.date = "2025-11-30"

        s.save(_make_index([card]))
        loaded = s.load()
        assert loaded is not None
        loaded_card = list(loaded.documents.values())[0]
        assert loaded_card.date == "2025-11-30"

    def test_null_date_preserved(self, tmp_path: Path) -> None:
        """date=None roundtrips correctly."""
        s = SqliteStorage(tmp_path / "index.db")
        card = _make_card(enriched=True)
        assert card.date is None
        s.save(_make_index([card]))
        loaded = s.load()
        assert loaded is not None
        loaded_card = list(loaded.documents.values())[0]
        assert loaded_card.date is None


class TestJsonDateRoundtrip:
    """date field roundtrip in JSON backend."""

    def test_date_roundtrip_json(self, tmp_path: Path) -> None:
        s = JsonStorage(tmp_path / "index.json")
        card = _make_card(enriched=True)
        card.date = "2025-11-30"
        s.save(_make_index([card]))
        loaded = s.load()
        assert loaded is not None
        loaded_card = list(loaded.documents.values())[0]
        assert loaded_card.date == "2025-11-30"

    def test_legacy_json_no_date_field(self, tmp_path: Path) -> None:
        """Old JSON index without date field loads with date=None."""
        index_path = tmp_path / ".doc-index.json"
        # Hand-craft a legacy JSON without the date field
        index_path.write_text(
            """{
              "version": "0.9.3",
              "indexed_at": "2026-01-01T00:00:00+00:00",
              "documents": {
                "proj::doc.md": {
                  "project": "proj",
                  "filename": "doc.md",
                  "rel_path": "doc.md",
                  "size": 100,
                  "modified": "2026-01-01T00:00:00+00:00",
                  "content_hash": "abc123",
                  "type": "spec",
                  "summary": "A spec"
                }
              }
            }"""
        )
        s = JsonStorage(index_path)
        loaded = s.load()
        assert loaded is not None
        assert loaded.documents["proj::doc.md"].date is None
