"""Tests for astrolabe.server."""

import json
from pathlib import Path

import pytest

import astrolabe.server as srv
from astrolabe import __version__
from astrolabe.models import AppConfig


@pytest.fixture
def server_env(tmp_path: Path, fake_project: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    """Set up server environment with config and index."""
    config = AppConfig(
        projects={"test-project": fake_project},
        index_dir=tmp_path,
        index_extensions=[".md", ".yaml", ".yml", ".txt"],
        ignore_dirs=[".git", ".venv", "src", "node_modules", "__pycache__"],
        ignore_files=["*.pyc", "*.lock"],
        max_file_size_kb=100,
    )

    # Write config.json
    config_file = tmp_path / "config.json"
    config_data = {
        "projects": {k: str(v) for k, v in config.projects.items()},
        "index_dir": ".",
        "index_extensions": config.index_extensions,
        "ignore_dirs": config.ignore_dirs,
        "ignore_files": config.ignore_files,
        "max_file_size_kb": config.max_file_size_kb,
    }
    config_file.write_text(json.dumps(config_data))

    # Write doc_types.yaml
    doc_types_file = tmp_path / "doc_types.yaml"
    doc_types_file.write_text(
        "document_types:\n"
        "  reference:\n"
        "    description: Reference material\n"
        "  instruction:\n"
        "    description: Project instruction\n"
    )

    monkeypatch.setenv("ASTROLABE_CONFIG", str(config_file))

    # Reset server global state
    srv._config = None
    srv._index = None
    srv._doc_types = {}

    # Initialize
    srv._init()

    return config


class TestGetCosmos:
    def test_returns_stats(self, server_env: AppConfig) -> None:
        result = srv.get_cosmos()
        assert result["server_version"] == __version__
        assert result["total_documents"] == 5
        assert result["empty_documents"] == 5  # nothing enriched
        assert len(result["projects"]) == 1
        assert result["projects"][0]["id"] == "test-project"

    def test_cosmos_after_enrichment(self, server_env: AppConfig) -> None:
        # Enrich one card
        assert srv._index is not None
        cards = list(srv._index.documents.keys())
        srv.update_index_tool(doc_id=cards[0], type="reference", summary="Test")

        result = srv.get_cosmos()
        assert result["enriched_documents"] == 1
        assert result["empty_documents"] == 4
        assert len(result["document_types"]) == 1
        assert result["document_types"][0]["type"] == "reference"


class TestListDocs:
    def test_lists_all(self, server_env: AppConfig) -> None:
        result = srv.list_docs()
        assert len(result) == 5

    def test_filter_by_project(self, server_env: AppConfig) -> None:
        result = srv.list_docs(project="test-project")
        assert len(result) == 5
        result = srv.list_docs(project="nonexistent")
        assert len(result) == 0

    def test_filter_stale(self, server_env: AppConfig) -> None:
        result = srv.list_docs(stale=True)
        assert len(result) == 5  # all are empty = stale


class TestSearchDocs:
    def test_search_by_filename(self, server_env: AppConfig) -> None:
        result = srv.search_docs(query="README")
        assert len(result) >= 1
        assert any("README" in r["filename"] for r in result)

    def test_search_enriched(self, server_env: AppConfig) -> None:
        assert srv._index is not None
        # Enrich a card
        doc_id = "test-project::README.md"
        srv.update_index_tool(
            doc_id=doc_id,
            type="project_doc",
            summary="Main project readme with setup instructions",
            keywords=["setup", "installation"],
        )

        result = srv.search_docs(query="setup installation")
        assert len(result) >= 1
        assert result[0]["doc_id"] == doc_id


class TestGetCard:
    def test_card_existing(self, server_env: AppConfig) -> None:
        result = srv.get_card(doc_id="test-project::README.md")
        assert result["doc_id"] == "test-project::README.md"
        assert result["filename"] == "README.md"

    def test_card_nonexistent(self, server_env: AppConfig) -> None:
        result = srv.get_card(doc_id="test-project::ghost.md")
        assert "error" in result


class TestReadDoc:
    def test_read_full_content(self, server_env: AppConfig) -> None:
        result = srv.read_doc(doc_id="test-project::README.md")
        assert "content" in result
        assert "My Project" in result["content"]

    def test_read_section(self, server_env: AppConfig) -> None:
        result = srv.read_doc(doc_id="test-project::docs/guide.md", section="Setup")
        assert "content" in result
        assert "Steps here." in result["content"]
        assert result.get("section") == "Setup"

    def test_read_range(self, server_env: AppConfig) -> None:
        result = srv.read_doc(doc_id="test-project::README.md", range="1-1")
        assert result["returned_lines"] == 1

    def test_read_nonexistent(self, server_env: AppConfig) -> None:
        result = srv.read_doc(doc_id="test-project::ghost.md")
        assert "error" in result


class TestUpdateIndex:
    def test_update_fields(self, server_env: AppConfig) -> None:
        result = srv.update_index_tool(
            doc_id="test-project::README.md",
            type="project_doc",
            summary="Main readme",
            keywords=["project", "readme"],
        )
        assert result["status"] == "updated"
        assert "type" in result["updated_fields"]
        assert "summary" in result["updated_fields"]

    def test_update_nonexistent(self, server_env: AppConfig) -> None:
        result = srv.update_index_tool(doc_id="ghost::doc.md", type="spec")
        assert "error" in result

    def test_partial_update(self, server_env: AppConfig) -> None:
        srv.update_index_tool(
            doc_id="test-project::README.md",
            type="project_doc",
            summary="Old summary",
        )
        result = srv.update_index_tool(
            doc_id="test-project::README.md",
            keywords=["new", "keywords"],
        )
        assert result["updated_fields"] == ["keywords"]
        # Check type preserved
        card_result = srv.get_card(doc_id="test-project::README.md")
        assert card_result["type"] == "project_doc"


class TestReindex:
    def test_reindex_all(self, server_env: AppConfig, fake_project: Path) -> None:
        result = srv.reindex_tool()
        assert result["unchanged"] == 5
        assert result["new"] == 0

    def test_reindex_detects_new_file(self, server_env: AppConfig, fake_project: Path) -> None:
        (fake_project / "new_doc.md").write_text("# New\n\nContent")
        result = srv.reindex_tool()
        assert result["new"] == 1

    def test_reindex_single_project(self, server_env: AppConfig, fake_project: Path) -> None:
        result = srv.reindex_tool(project="test-project")
        assert result["unchanged"] == 5

    def test_reindex_nonexistent_project(self, server_env: AppConfig) -> None:
        result = srv.reindex_tool(project="ghost")
        assert "error" in result


class TestDocTypesLookup:
    """Test doc_types.yaml lookup order: index_dir first, config_path.parent fallback."""

    def _setup_split_dirs(
        self,
        tmp_path: Path,
        fake_project: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        yaml_in_cloud: bool = False,
        yaml_in_config: bool = False,
        cloud_content: str = "",
        config_content: str = "",
    ) -> None:
        config_dir = tmp_path / "config"
        cloud_dir = tmp_path / "cloud"
        config_dir.mkdir()
        cloud_dir.mkdir()

        config_file = config_dir / "config.json"
        config_data = {
            "projects": {"test-project": str(fake_project)},
            "index_dir": str(cloud_dir),
            "index_extensions": [".md", ".txt"],
            "ignore_dirs": [".git"],
            "ignore_files": [],
            "max_file_size_kb": 100,
        }
        config_file.write_text(json.dumps(config_data))

        if yaml_in_cloud:
            (cloud_dir / "doc_types.yaml").write_text(cloud_content)
        if yaml_in_config:
            (config_dir / "doc_types.yaml").write_text(config_content)

        monkeypatch.setenv("ASTROLABE_CONFIG", str(config_file))
        srv._config = None
        srv._index = None
        srv._doc_types = {}
        srv._init()

    def test_loads_from_index_parent(
        self, tmp_path: Path, fake_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup_split_dirs(
            tmp_path,
            fake_project,
            monkeypatch,
            yaml_in_cloud=True,
            cloud_content=("document_types:\n  cloud_type:\n    description: From cloud\n"),
        )
        assert "cloud_type" in srv._doc_types

    def test_fallback_to_config_parent(
        self, tmp_path: Path, fake_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup_split_dirs(
            tmp_path,
            fake_project,
            monkeypatch,
            yaml_in_config=True,
            config_content=("document_types:\n  local_type:\n    description: From config\n"),
        )
        assert "local_type" in srv._doc_types

    def test_index_parent_takes_precedence(
        self, tmp_path: Path, fake_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._setup_split_dirs(
            tmp_path,
            fake_project,
            monkeypatch,
            yaml_in_cloud=True,
            yaml_in_config=True,
            cloud_content=("document_types:\n  cloud_type:\n    description: From cloud\n"),
            config_content=("document_types:\n  local_type:\n    description: From config\n"),
        )
        assert "cloud_type" in srv._doc_types
        assert "local_type" not in srv._doc_types
