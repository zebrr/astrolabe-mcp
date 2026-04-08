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
    srv._storage = None
    srv._private_storage = None
    srv._doc_types = {}
    srv._doc_types_full = {}
    srv._embedding_backend = None
    srv._private_embedding_backend = None

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
        assert result["total"] == 5
        assert len(result["result"]) == 5
        assert "limit" in result
        assert "offset" in result

    def test_filter_by_project(self, server_env: AppConfig) -> None:
        result = srv.list_docs(project="test-project")
        assert result["total"] == 5
        result = srv.list_docs(project="nonexistent")
        assert result["total"] == 0
        assert len(result["result"]) == 0

    def test_filter_stale(self, server_env: AppConfig) -> None:
        result = srv.list_docs(stale=True)
        assert result["total"] == 5  # all are empty = stale

    def test_limit_default(self, server_env: AppConfig) -> None:
        result = srv.list_docs()
        assert result["limit"] == 50  # config default

    def test_limit_custom(self, server_env: AppConfig) -> None:
        result = srv.list_docs(limit=2)
        assert result["limit"] == 2
        assert len(result["result"]) == 2
        assert result["total"] == 5

    def test_offset(self, server_env: AppConfig) -> None:
        result = srv.list_docs(offset=3)
        assert len(result["result"]) == 2  # 5 total, skip 3
        assert result["offset"] == 3

    def test_offset_beyond_total(self, server_env: AppConfig) -> None:
        result = srv.list_docs(offset=100)
        assert len(result["result"]) == 0
        assert "hint" in result

    def test_hint_without_filters(self, server_env: AppConfig) -> None:
        result = srv.list_docs(limit=2)
        assert "hint" in result
        assert "Showing 2 of 5" in result["hint"]
        assert "Narrow by project" in result["hint"]
        assert "Narrow by type" in result["hint"]
        assert "Next page: offset=2" in result["hint"]

    def test_hint_with_project_filter(self, server_env: AppConfig) -> None:
        result = srv.list_docs(project="test-project", limit=2)
        assert "hint" in result
        # Should suggest narrowing by type, not by project
        assert "Narrow by type" in result["hint"]
        assert "Narrow by project" not in result["hint"]

    def test_no_timestamps_in_result(self, server_env: AppConfig) -> None:
        result = srv.list_docs()
        for item in result["result"]:
            assert "modified" not in item
            assert "enriched_at" not in item


class TestDesync:
    """Tests for desync visibility: per-project count in cosmos, desync filter in list_docs."""

    def test_cosmos_no_desync(self, server_env: AppConfig) -> None:
        result = srv.get_cosmos()
        assert result["desync_documents"] == 0
        assert result["projects"][0]["desync_count"] == 0

    def test_cosmos_desync_count(self, server_env: AppConfig, fake_project: Path) -> None:
        # Delete a file to create desync
        (fake_project / "README.md").unlink()
        result = srv.get_cosmos()
        assert result["desync_documents"] == 1
        assert result["projects"][0]["desync_count"] == 1

    def test_list_docs_desync_filter(self, server_env: AppConfig, fake_project: Path) -> None:
        (fake_project / "README.md").unlink()
        result = srv.list_docs(desync=True)
        assert result["total"] == 1
        assert result["result"][0]["filename"] == "README.md"

    def test_list_docs_desync_with_project_filter(
        self, server_env: AppConfig, fake_project: Path
    ) -> None:
        (fake_project / "README.md").unlink()
        result = srv.list_docs(project="test-project", desync=True)
        assert result["total"] == 1
        result = srv.list_docs(project="nonexistent", desync=True)
        assert result["total"] == 0

    def test_list_docs_no_desync(self, server_env: AppConfig) -> None:
        # No files deleted — desync filter returns nothing
        result = srv.list_docs(desync=True)
        assert result["total"] == 0

    def test_passthrough_not_counted_as_desync(self, server_env: AppConfig) -> None:
        # Manually add a card from an unconfigured project
        from astrolabe.models import DocCard

        assert srv._index is not None
        card = DocCard(
            project="foreign-project",
            filename="doc.md",
            rel_path="doc.md",
            size=100,
            modified=srv._index.indexed_at,
            content_hash="abc123",
        )
        srv._index.documents[card.doc_id] = card

        result = srv.get_cosmos()
        assert result["desync_documents"] == 0

        result = srv.list_docs(desync=True)
        assert result["total"] == 0


class TestSearchDocs:
    def test_search_by_filename(self, server_env: AppConfig) -> None:
        result = srv.search_docs(query="README")
        assert result["total"] >= 1
        assert any("README" in r["filename"] for r in result["result"])
        assert "max_results" in result

    def test_search_enriched(self, server_env: AppConfig) -> None:
        assert srv._index is not None
        # Enrich a card
        doc_id = "test-project::README.md"
        srv.update_index_tool(
            doc_id=doc_id,
            type="reference",
            summary="Main project readme with setup instructions",
            keywords=["setup", "installation"],
        )

        result = srv.search_docs(query="setup installation")
        assert result["total"] >= 1
        assert result["result"][0]["doc_id"] == doc_id

    def test_max_results_default(self, server_env: AppConfig) -> None:
        result = srv.search_docs(query="md")
        assert result["max_results"] == 20  # config default

    def test_max_results_custom(self, server_env: AppConfig) -> None:
        result = srv.search_docs(query="md", max_results=1)
        assert result["max_results"] == 1
        assert len(result["result"]) <= 1

    def test_search_hint_on_truncation(self, server_env: AppConfig) -> None:
        # With max_results=1, if >1 match exists we get a hint
        result = srv.search_docs(query="md", max_results=1)
        if result["total"] > 1:
            assert "hint" in result
            assert "Showing top 1" in result["hint"]


class TestGetCard:
    def test_card_existing(self, server_env: AppConfig) -> None:
        result = srv.get_card(doc_id="test-project::README.md")
        assert result["doc_id"] == "test-project::README.md"
        assert result["filename"] == "README.md"

    def test_card_has_stale_flag(self, server_env: AppConfig) -> None:
        result = srv.get_card(doc_id="test-project::README.md")
        assert "stale" in result
        assert result["stale"] is False  # not enriched = not stale (is_empty)

    def test_card_stale_after_content_change(self, server_env: AppConfig) -> None:
        # Enrich a card
        srv.update_index_tool(doc_id="test-project::README.md", type="reference", summary="Test")
        # Simulate content change by modifying enriched_content_hash
        assert srv._index is not None
        card = srv._index.documents["test-project::README.md"]
        card.content_hash = "changed_hash"

        result = srv.get_card(doc_id="test-project::README.md")
        assert result["stale"] is True

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

    def test_truncation_hint_has_sections(self, server_env: AppConfig, fake_project: Path) -> None:
        # Create a large file with headings, reindex
        content = "# Title\n\n## Setup\n\nText.\n\n## Usage\n\nMore text.\n\n"
        content += "x" * (101 * 1024)  # exceeds 100KB max_file_size_kb
        (fake_project / "big.md").write_text(content)
        srv.reindex_tool()

        result = srv.read_doc(doc_id="test-project::big.md")
        assert result.get("truncated") is True
        assert "hint" in result
        assert "Available sections" in result["hint"]
        assert "Title" in result["hint"]
        assert "Setup" in result["hint"]
        assert result["available_sections"] == ["Title", "Setup", "Usage"]


class TestUpdateIndex:
    def test_update_fields(self, server_env: AppConfig) -> None:
        result = srv.update_index_tool(
            doc_id="test-project::README.md",
            type="reference",
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
            type="reference",
            summary="Old summary",
        )
        result = srv.update_index_tool(
            doc_id="test-project::README.md",
            keywords=["new", "keywords"],
        )
        assert result["updated_fields"] == ["keywords"]
        # Check type preserved
        card_result = srv.get_card(doc_id="test-project::README.md")
        assert card_result["type"] == "reference"


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


class TestGetDocTypes:
    def test_returns_full_vocabulary(self, server_env: AppConfig) -> None:
        result = srv.get_doc_types()
        assert "reference" in result
        assert "instruction" in result
        assert result["reference"]["description"] == "Reference material"

    def test_empty_when_no_yaml(
        self, tmp_path: Path, fake_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "config.json"
        config_data = {
            "projects": {"test-project": str(fake_project)},
            "index_dir": str(tmp_path / "no-yaml-here"),
            "index_extensions": [".md"],
            "ignore_dirs": [".git"],
            "ignore_files": [],
            "max_file_size_kb": 100,
        }
        (tmp_path / "no-yaml-here").mkdir()
        config_file.write_text(json.dumps(config_data))
        monkeypatch.setenv("ASTROLABE_CONFIG", str(config_file))
        srv._config = None
        srv._index = None
        srv._doc_types = {}
        srv._doc_types_full = {}
        srv._init()

        result = srv.get_doc_types()
        assert result == {}


class TestTypeValidation:
    def test_rejects_unknown_type(self, server_env: AppConfig) -> None:
        result = srv.update_index_tool(
            doc_id="test-project::README.md",
            type="invented_type",
        )
        assert "error" in result
        assert "Unknown type" in result["error"]
        assert "Available types" in result["error"]

    def test_accepts_valid_type(self, server_env: AppConfig) -> None:
        result = srv.update_index_tool(
            doc_id="test-project::README.md",
            type="reference",
            summary="Test summary",
        )
        assert result["status"] == "updated"

    def test_no_validation_without_doc_types(
        self, tmp_path: Path, fake_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When doc_types.yaml is missing, any type is accepted."""
        config_file = tmp_path / "config.json"
        config_data = {
            "projects": {"test-project": str(fake_project)},
            "index_dir": str(tmp_path / "no-yaml"),
            "index_extensions": [".md"],
            "ignore_dirs": [".git"],
            "ignore_files": [],
            "max_file_size_kb": 100,
        }
        (tmp_path / "no-yaml").mkdir()
        config_file.write_text(json.dumps(config_data))
        monkeypatch.setenv("ASTROLABE_CONFIG", str(config_file))
        srv._config = None
        srv._index = None
        srv._doc_types = {}
        srv._doc_types_full = {}
        srv._init()

        result = srv.update_index_tool(
            doc_id="test-project::README.md",
            type="any_type_works",
            summary="No validation",
        )
        assert result["status"] == "updated"


class TestPrivateIndex:
    """Tests for private index: dual storage, routing, merge."""

    @pytest.fixture
    def private_env(
        self, tmp_path: Path, fake_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[AppConfig, Path]:
        """Set up server with both shared and private projects."""
        # Create private project
        private_proj = tmp_path / "private-proj"
        private_proj.mkdir()
        (private_proj / "secret.md").write_text("# Secret\n\nPrivate content.")
        (private_proj / "notes.md").write_text("# Notes\n\nPrivate notes.")

        shared_dir = tmp_path / "shared-idx"
        private_dir = tmp_path / "private-idx"
        shared_dir.mkdir()
        private_dir.mkdir()

        config_file = tmp_path / "config.json"
        config_data = {
            "projects": {"test-project": str(fake_project)},
            "index_dir": str(shared_dir),
            "private_projects": {"private-proj": str(private_proj)},
            "private_index_dir": str(private_dir),
            "index_extensions": [".md", ".yaml", ".yml", ".txt"],
            "ignore_dirs": [".git", ".venv", "src", "node_modules", "__pycache__"],
            "ignore_files": ["*.pyc", "*.lock"],
            "max_file_size_kb": 100,
        }
        config_file.write_text(json.dumps(config_data))

        doc_types_file = shared_dir / "doc_types.yaml"
        doc_types_file.write_text(
            "document_types:\n"
            "  reference:\n"
            "    description: Reference material\n"
            "  instruction:\n"
            "    description: Project instruction\n"
        )

        monkeypatch.setenv("ASTROLABE_CONFIG", str(config_file))
        srv._config = None
        srv._index = None
        srv._storage = None
        srv._private_storage = None
        srv._doc_types = {}
        srv._doc_types_full = {}
        srv._init()

        assert srv._config is not None
        return srv._config, private_proj

    def test_unified_index_has_both(self, private_env: tuple[AppConfig, Path]) -> None:
        """_index contains cards from both shared and private projects."""
        assert srv._index is not None
        projects = {c.project for c in srv._index.documents.values()}
        assert "test-project" in projects
        assert "private-proj" in projects

    def test_cosmos_shows_all_projects(self, private_env: tuple[AppConfig, Path]) -> None:
        result = srv.get_cosmos()
        project_ids = [p["id"] for p in result["projects"]]
        assert "test-project" in project_ids
        assert "private-proj" in project_ids

    def test_list_docs_includes_private(self, private_env: tuple[AppConfig, Path]) -> None:
        result = srv.list_docs(project="private-proj")
        assert result["total"] == 2
        filenames = {r["filename"] for r in result["result"]}
        assert "secret.md" in filenames
        assert "notes.md" in filenames

    def test_search_finds_private(self, private_env: tuple[AppConfig, Path]) -> None:
        # Enrich a private card
        srv.update_index_tool(
            doc_id="private-proj::secret.md",
            type="reference",
            summary="Secret document with private content",
            keywords=["secret", "private"],
        )
        result = srv.search_docs(query="secret private")
        assert result["total"] >= 1
        assert any(r["doc_id"] == "private-proj::secret.md" for r in result["result"])

    def test_read_doc_private(self, private_env: tuple[AppConfig, Path]) -> None:
        result = srv.read_doc(doc_id="private-proj::secret.md")
        assert "content" in result
        assert "Private content" in result["content"]

    def test_update_routes_to_private_storage(self, private_env: tuple[AppConfig, Path]) -> None:
        """Enriching a private card saves to private storage, not shared."""
        srv.update_index_tool(
            doc_id="private-proj::secret.md",
            type="reference",
            summary="A secret doc",
        )

        # Verify private storage has the card
        assert srv._private_storage is not None
        private_data = srv._private_storage.load()
        assert private_data is not None
        assert "private-proj::secret.md" in private_data.documents
        assert private_data.documents["private-proj::secret.md"].type == "reference"

        # Verify shared storage does NOT have the private card
        assert srv._storage is not None
        shared_data = srv._storage.load()
        assert shared_data is not None
        assert "private-proj::secret.md" not in shared_data.documents

    def test_update_routes_to_shared_storage(self, private_env: tuple[AppConfig, Path]) -> None:
        """Enriching a shared card saves to shared storage."""
        srv.update_index_tool(
            doc_id="test-project::README.md",
            type="reference",
            summary="Main readme",
        )

        assert srv._storage is not None
        shared_data = srv._storage.load()
        assert shared_data is not None
        assert "test-project::README.md" in shared_data.documents

    def test_reindex_preserves_split(self, private_env: tuple[AppConfig, Path]) -> None:
        """After reindex, shared and private cards go to correct storages."""
        srv.reindex_tool()

        assert srv._storage is not None
        assert srv._private_storage is not None

        shared_data = srv._storage.load()
        private_data = srv._private_storage.load()

        assert shared_data is not None
        assert private_data is not None

        shared_projects = {c.project for c in shared_data.documents.values()}
        private_projects = {c.project for c in private_data.documents.values()}

        assert "test-project" in shared_projects
        assert "private-proj" not in shared_projects
        assert "private-proj" in private_projects

    def test_reindex_single_private_project(self, private_env: tuple[AppConfig, Path]) -> None:
        _, private_proj = private_env
        result = srv.reindex_tool(project="private-proj")
        assert "error" not in result
        assert result["unchanged"] == 2

    def test_backward_compat_no_private(self, server_env: AppConfig) -> None:
        """Without private config, behavior is identical to v0.3.1."""
        assert srv._private_storage is None
        result = srv.get_cosmos()
        assert len(result["projects"]) == 1


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
        srv._doc_types_full = {}
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


class TestContentDedup:
    """Tests for content deduplication across search, list, and get_card."""

    @pytest.fixture
    def dedup_env(
        self, tmp_path: Path, fake_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Set up two projects with an identical file to test dedup."""
        # Create second project with a file identical to README.md
        proj_b = tmp_path / "proj-b"
        proj_b.mkdir()
        # Copy exact content from fake_project README.md
        readme_content = (fake_project / "README.md").read_text()
        (proj_b / "README.md").write_text(readme_content)
        # Also a unique file
        (proj_b / "unique.md").write_text("# Unique content in proj-b")

        config_file = tmp_path / "config.json"
        config_data = {
            "projects": {
                "test-project": str(fake_project),
                "proj-b": str(proj_b),
            },
            "index_dir": str(tmp_path),
            "index_extensions": [".md", ".yaml", ".yml", ".txt"],
            "ignore_dirs": [".git", ".venv", "src", "node_modules", "__pycache__"],
            "ignore_files": ["*.pyc", "*.lock"],
            "max_file_size_kb": 100,
        }
        config_file.write_text(json.dumps(config_data))

        doc_types_file = tmp_path / "doc_types.yaml"
        doc_types_file.write_text(
            "document_types:\n  reference:\n    description: Reference material\n"
        )

        monkeypatch.setenv("ASTROLABE_CONFIG", str(config_file))
        srv._config = None
        srv._index = None
        srv._storage = None
        srv._private_storage = None
        srv._doc_types = {}
        srv._doc_types_full = {}
        srv._init()

    def test_search_dedup_same_hash(self, dedup_env: None) -> None:
        """Search returns only one result per content_hash."""
        result = srv.search_docs(query="README")
        readme_results = [r for r in result["result"] if r["filename"] == "README.md"]
        assert len(readme_results) == 1

    def test_search_dedup_total_reflects_dedup(self, dedup_env: None) -> None:
        """Total count in search is post-dedup."""
        result = srv.search_docs(query="README")
        # Only one README should be counted
        readme_count = sum(1 for r in result["result"] if r["filename"] == "README.md")
        assert readme_count == 1

    def test_search_unique_not_affected(self, dedup_env: None) -> None:
        """Unique documents are not affected by dedup."""
        result = srv.search_docs(query="unique proj-b")
        unique_results = [r for r in result["result"] if r["filename"] == "unique.md"]
        assert len(unique_results) == 1

    def test_list_has_copies_present(self, dedup_env: None) -> None:
        """list_docs marks cards with has_copies=True when duplicates exist."""
        result = srv.list_docs()
        readmes = [r for r in result["result"] if r["filename"] == "README.md"]
        assert len(readmes) == 2  # both shown
        for r in readmes:
            assert r.get("has_copies") is True

    def test_list_no_copies_absent(self, dedup_env: None) -> None:
        """list_docs omits has_copies for unique documents."""
        result = srv.list_docs()
        uniques = [r for r in result["result"] if r["filename"] == "unique.md"]
        assert len(uniques) == 1
        assert "has_copies" not in uniques[0]

    def test_get_card_copies_field(self, dedup_env: None) -> None:
        """get_card includes copies list for duplicated documents."""
        result = srv.get_card(doc_id="test-project::README.md")
        assert "copies" in result
        assert "proj-b::README.md" in result["copies"]

    def test_get_card_no_copies_for_unique(self, dedup_env: None) -> None:
        """get_card omits copies for unique documents."""
        result = srv.get_card(doc_id="proj-b::unique.md")
        assert "copies" not in result


class TestDeepSearch:
    """Tests for deep_search tool."""

    def test_disabled_returns_error(self, server_env: AppConfig) -> None:
        """deep_search returns error when embeddings not enabled."""
        result = srv.deep_search(query="test")
        assert "error" in result
        assert "not enabled" in result["error"]
        assert "hint" in result

    def test_search_docs_no_embed_hint_when_disabled(self, server_env: AppConfig) -> None:
        """search_docs does not hint at deep_search when embeddings disabled."""
        result = srv.search_docs(query="nonexistent_term_xyz")
        if "hint" in result:
            assert "deep_search" not in result["hint"]

    def test_search_docs_still_fast(self, server_env: AppConfig) -> None:
        """search_docs returns results without embedding overhead."""
        srv.update_index_tool(
            doc_id="test-project::README.md",
            type="reference",
            summary="Project readme",
            keywords=["readme", "setup"],
        )
        result = srv.search_docs(query="readme")
        assert result["total"] >= 1
        assert result["result"][0]["doc_id"] == "test-project::README.md"
