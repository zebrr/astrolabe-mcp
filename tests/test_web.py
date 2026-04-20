"""Tests for astrolabe web UI."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from astrolabe.models import AppConfig, DocCard, IndexData
from astrolabe.web.app import create_app
from astrolabe.web.state import AppState


@pytest.fixture()
def sample_config(tmp_path: Path) -> AppConfig:
    """Create a sample config with a test project."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    (project_dir / "README.md").write_text("# Test\nHello world\n")
    (project_dir / "notes.txt").write_text("Some notes\n")

    return AppConfig(
        projects={"test-project": project_dir},
        index_dir=tmp_path,
        storage="json",
        index_extensions=[".md", ".txt"],
        ignore_dirs=[],
        ignore_files=[],
        max_file_size_kb=100,
    )


@pytest.fixture()
def sample_index() -> IndexData:
    """Create a sample index with test cards."""
    now = datetime.now(UTC)
    cards: dict[str, DocCard] = {
        "test-project::README.md": DocCard(
            project="test-project",
            filename="README.md",
            rel_path="README.md",
            size=25,
            modified=now,
            content_hash="abc123",
            type="document",
            summary="A test readme file",
            keywords=["test", "readme"],
            headings=["Test"],
            enriched_at=now,
            enriched_content_hash="abc123",
        ),
        "test-project::notes.txt": DocCard(
            project="test-project",
            filename="notes.txt",
            rel_path="notes.txt",
            size=11,
            modified=now,
            content_hash="def456",
        ),
    }
    return IndexData(indexed_at=now, documents=cards)


@pytest.fixture()
def app_state(sample_config: AppConfig, sample_index: IndexData, tmp_path: Path) -> AppState:
    """Create an AppState with sample data."""
    from astrolabe.storage_json import JsonStorage

    storage = JsonStorage(tmp_path / ".doc-index.json")
    storage.save(sample_index)

    return AppState(
        config=sample_config,
        config_path=tmp_path / "config.json",
        index=sample_index,
        storage=storage,
        private_storage=None,
        doc_types_full={
            "document": {"description": "Concept, architecture, README"},
            "reference": {"description": "Reference material"},
            "spec": {"description": "Technical specification"},
        },
    )


@pytest.fixture()
def client(app_state: AppState) -> TestClient:
    """Create a test client with mocked state."""
    app = create_app()
    app.state.astrolabe = app_state
    return TestClient(app, raise_server_exceptions=True)


class TestDashboard:
    """Tests for the dashboard page."""

    def test_dashboard_loads(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_dashboard_shows_stats(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "2" in resp.text  # total documents
        assert "test-project" in resp.text

    def test_dashboard_has_clickable_project(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "/cards?project=test-project" in resp.text


class TestCardList:
    """Tests for the card list page."""

    def test_cards_page_loads(self, client: TestClient) -> None:
        resp = client.get("/cards")
        assert resp.status_code == 200
        assert "README.md" in resp.text
        assert "notes.txt" in resp.text

    def test_cards_filter_by_project(self, client: TestClient) -> None:
        resp = client.get("/cards?project=test-project")
        assert resp.status_code == 200
        assert "README.md" in resp.text

    def test_cards_filter_empty(self, client: TestClient) -> None:
        resp = client.get("/cards?empty=true")
        assert resp.status_code == 200
        assert "notes.txt" in resp.text
        # README.md is enriched, should not appear
        assert "README.md" not in resp.text

    def test_cards_filter_by_type(self, client: TestClient) -> None:
        resp = client.get("/cards?type=document")
        assert resp.status_code == 200
        assert "README.md" in resp.text


class TestCardDetail:
    """Tests for the card detail page."""

    def test_card_detail_loads(self, client: TestClient) -> None:
        resp = client.get("/cards/test-project::README.md")
        assert resp.status_code == 200
        assert "README.md" in resp.text
        assert "document" in resp.text
        assert "A test readme file" in resp.text

    def test_card_detail_not_found(self, client: TestClient) -> None:
        resp = client.get("/cards/test-project::nonexistent.md")
        assert resp.status_code == 404

    def test_card_has_edit_button(self, client: TestClient) -> None:
        resp = client.get("/cards/test-project::README.md")
        assert "Edit" in resp.text

    def test_card_has_read_link(self, client: TestClient) -> None:
        resp = client.get("/cards/test-project::README.md")
        assert "/read/" in resp.text


class TestCardEdit:
    """Tests for card inline editing."""

    def test_edit_form_loads(self, client: TestClient) -> None:
        resp = client.get("/api/cards/test-project::README.md/edit")
        assert resp.status_code == 200
        assert "Save" in resp.text
        assert "Cancel" in resp.text
        assert "textarea" in resp.text

    def test_save_card(self, client: TestClient, app_state: AppState) -> None:
        resp = client.post(
            "/api/cards/test-project::README.md/save",
            data={
                "type": "reference",
                "summary": "Updated summary",
                "keywords": "new, keywords",
                "headings": "Heading One, Heading Two",
            },
        )
        assert resp.status_code == 200
        assert "Card updated" in resp.text

        # Verify the card was updated
        card = app_state.index.documents["test-project::README.md"]
        assert card.type == "reference"
        assert card.summary == "Updated summary"
        assert card.keywords == ["new", "keywords"]
        assert card.headings == ["Heading One", "Heading Two"]

    def test_save_invalid_type(self, client: TestClient) -> None:
        resp = client.post(
            "/api/cards/test-project::README.md/save",
            data={"type": "invalid_type", "summary": "", "keywords": "", "headings": ""},
        )
        assert resp.status_code == 200
        assert "Unknown type" in resp.text

    def test_cancel_edit(self, client: TestClient) -> None:
        resp = client.post("/api/cards/test-project::README.md/cancel")
        assert resp.status_code == 200
        assert "Edit" in resp.text  # back to view mode


class TestDocReader:
    """Tests for the document reader page."""

    def test_read_markdown(self, client: TestClient) -> None:
        resp = client.get("/read/test-project::README.md")
        assert resp.status_code == 200
        # Markdown should be rendered to HTML
        assert "<h1>" in resp.text or "Test" in resp.text

    def test_read_plaintext(self, client: TestClient) -> None:
        resp = client.get("/read/test-project::notes.txt")
        assert resp.status_code == 200
        assert "Some notes" in resp.text

    def test_read_not_found(self, client: TestClient) -> None:
        resp = client.get("/read/test-project::nonexistent.md")
        assert resp.status_code == 404


class TestSearch:
    """Tests for the search page."""

    def test_search_page_loads(self, client: TestClient) -> None:
        resp = client.get("/search")
        assert resp.status_code == 200
        assert "Search" in resp.text

    def test_search_query(self, client: TestClient) -> None:
        resp = client.post("/api/search", data={"query": "readme"})
        assert resp.status_code == 200
        assert "README.md" in resp.text

    def test_search_empty_query(self, client: TestClient) -> None:
        resp = client.post("/api/search", data={"query": ""})
        assert resp.status_code == 200
        assert "Enter a search query" in resp.text


class TestReindex:
    """Tests for reindex and refresh actions."""

    def test_reindex_update(self, client: TestClient) -> None:
        resp = client.post("/api/reindex", data={"mode": "update", "project": ""})
        assert resp.status_code == 200
        assert "scanned" in resp.text

    def test_reindex_invalid_mode(self, client: TestClient) -> None:
        resp = client.post("/api/reindex", data={"mode": "invalid", "project": ""})
        assert resp.status_code == 400

    def test_reindex_storage_error_returns_toast(
        self, client: TestClient, app_state: AppState
    ) -> None:
        """Storage errors during reindex return error toast, not 500."""
        from unittest.mock import patch

        with patch.object(
            app_state, "do_reindex", side_effect=Exception("attempt to write a readonly database")
        ):
            resp = client.post("/api/reindex", data={"mode": "update", "project": ""})

        assert resp.status_code == 200
        assert "Reindex failed" in resp.text
        assert "readonly" in resp.text

    def test_refresh(self, client: TestClient) -> None:
        resp = client.post("/api/refresh")
        assert resp.status_code == 200
        assert "Reloaded" in resp.text


class TestAcceptDivergenceEndpoint:
    def test_accept_clears_flag_and_persists(
        self, client: TestClient, app_state: AppState
    ) -> None:
        card = app_state.index.documents["test-project::README.md"]
        card.diverged_from = ["other::a.md", "other::b.md"]

        resp = client.post("/api/cards/test-project::README.md/accept-divergence")
        assert resp.status_code == 200
        assert "Divergence accepted" in resp.text

        assert app_state.index.documents["test-project::README.md"].diverged_from is None
        # Persisted to storage
        reloaded = app_state.storage.load()
        assert reloaded is not None
        assert reloaded.documents["test-project::README.md"].diverged_from is None

    def test_accept_without_flag_returns_error(self, client: TestClient) -> None:
        resp = client.post("/api/cards/test-project::README.md/accept-divergence")
        assert resp.status_code == 200
        assert "No divergence" in resp.text

    def test_accept_missing_doc(self, client: TestClient) -> None:
        resp = client.post("/api/cards/nope::missing.md/accept-divergence")
        assert resp.status_code == 200
        assert "not found" in resp.text.lower()

    def test_cards_page_diverged_filter(self, client: TestClient, app_state: AppState) -> None:
        app_state.index.documents["test-project::README.md"].diverged_from = ["x::y.md"]
        resp = client.get("/cards?diverged=true")
        assert resp.status_code == 200
        assert "README.md" in resp.text
        # notes.txt is not diverged, so the mark for README should indicate divergence
        assert "diverged-mark" in resp.text or "Diverged" in resp.text

    def test_cosmos_shows_diverged_counter(self, client: TestClient, app_state: AppState) -> None:
        app_state.index.documents["test-project::README.md"].diverged_from = ["x::y.md"]
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Diverged" in resp.text
