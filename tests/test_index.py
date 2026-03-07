"""Tests for astrolabe.index."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from astrolabe import __version__
from astrolabe.index import (
    _compute_hash,
    build_index,
    load_index,
    reindex,
    save_index,
    scan_project,
    update_card,
)
from astrolabe.models import AppConfig, DocCard, IndexData


class TestScanProject:
    def test_finds_docs(self, fake_project: Path, sample_config: AppConfig) -> None:
        cards = scan_project("my-project", fake_project, sample_config)
        filenames = {c.filename for c in cards}
        assert "README.md" in filenames
        assert "CLAUDE.md" in filenames
        assert "guide.md" in filenames
        assert "notes.txt" in filenames
        assert "config.yaml" in filenames

    def test_ignores_git_dir(self, fake_project: Path, sample_config: AppConfig) -> None:
        cards = scan_project("my-project", fake_project, sample_config)
        paths = {c.rel_path for c in cards}
        assert not any(".git" in p for p in paths)

    def test_ignores_venv_dir(self, fake_project: Path, sample_config: AppConfig) -> None:
        cards = scan_project("my-project", fake_project, sample_config)
        paths = {c.rel_path for c in cards}
        assert not any(".venv" in p for p in paths)

    def test_ignores_src_dir(self, fake_project: Path, sample_config: AppConfig) -> None:
        cards = scan_project("my-project", fake_project, sample_config)
        paths = {c.rel_path for c in cards}
        assert not any("src/" in p for p in paths)

    def test_rel_path_is_posix(self, fake_project: Path, sample_config: AppConfig) -> None:
        cards = scan_project("my-project", fake_project, sample_config)
        for card in cards:
            assert "\\" not in card.rel_path

    def test_doc_id_format(self, fake_project: Path, sample_config: AppConfig) -> None:
        cards = scan_project("my-project", fake_project, sample_config)
        for card in cards:
            assert card.doc_id.startswith("my-project::")

    def test_content_hash_computed(self, fake_project: Path, sample_config: AppConfig) -> None:
        cards = scan_project("my-project", fake_project, sample_config)
        for card in cards:
            assert len(card.content_hash) == 32  # MD5 hex digest

    def test_nonexistent_path_returns_empty(self, sample_config: AppConfig) -> None:
        cards = scan_project("ghost", Path("/nonexistent"), sample_config)
        assert cards == []

    def test_ignore_files_pattern(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "good.md").write_text("content")
        (proj / "bad.pyc").write_text("bytecode")
        (proj / "deps.lock").write_text("lock")

        config = AppConfig(
            projects={"proj": proj},
            index_path=tmp_path / ".doc-index.json",
            index_extensions=[".md", ".pyc", ".lock"],
            ignore_dirs=[],
            ignore_files=["*.pyc", "*.lock"],
            max_file_size_kb=100,
        )
        cards = scan_project("proj", proj, config)
        filenames = {c.filename for c in cards}
        assert "good.md" in filenames
        assert "bad.pyc" not in filenames
        assert "deps.lock" not in filenames


class TestComputeHash:
    def test_crlf_and_lf_produce_same_hash(self, tmp_path: Path) -> None:
        lf_file = tmp_path / "lf.txt"
        crlf_file = tmp_path / "crlf.txt"
        lf_file.write_bytes(b"line1\nline2\nline3\n")
        crlf_file.write_bytes(b"line1\r\nline2\r\nline3\r\n")
        assert _compute_hash(lf_file) == _compute_hash(crlf_file)

    def test_isolated_cr_not_affected(self, tmp_path: Path) -> None:
        normal = tmp_path / "normal.txt"
        with_cr = tmp_path / "with_cr.txt"
        normal.write_bytes(b"hello\nworld")
        with_cr.write_bytes(b"hello\rworld")
        assert _compute_hash(normal) != _compute_hash(with_cr)

    def test_binary_content_stable(self, tmp_path: Path) -> None:
        f = tmp_path / "binary.bin"
        data = bytes(range(256))
        f.write_bytes(data)
        h1 = _compute_hash(f)
        h2 = _compute_hash(f)
        assert h1 == h2
        assert len(h1) == 32


class TestLoadSaveIndex:
    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        card = DocCard(
            project="proj",
            filename="doc.md",
            rel_path="doc.md",
            size=100,
            modified=datetime(2026, 3, 6, tzinfo=UTC),
            content_hash="abc123",
            type="spec",
            summary="A spec doc",
        )
        index = IndexData(
            indexed_at=datetime(2026, 3, 6, tzinfo=UTC),
            documents={card.doc_id: card},
        )

        index_path = tmp_path / ".doc-index.json"
        save_index(index, index_path)

        loaded = load_index(index_path)
        assert loaded is not None
        assert "proj::doc.md" in loaded.documents
        assert loaded.documents["proj::doc.md"].type == "spec"

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        result = load_index(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_corrupt_returns_none_and_backups(self, tmp_path: Path) -> None:
        index_path = tmp_path / ".doc-index.json"
        index_path.write_text("{invalid json")

        result = load_index(index_path)
        assert result is None
        assert (tmp_path / ".doc-index.json.bak").exists()

    def test_save_creates_parent_dirs_if_missing(self, tmp_path: Path) -> None:
        index_path = tmp_path / ".doc-index.json"
        index = IndexData(indexed_at=datetime(2026, 3, 6, tzinfo=UTC))
        save_index(index, index_path)
        assert index_path.exists()


class TestBuildIndex:
    def test_builds_from_config(self, fake_project: Path, sample_config: AppConfig) -> None:
        index = build_index(sample_config)
        assert len(index.documents) == 5  # README, CLAUDE, guide, notes, config
        assert index.version == __version__

    def test_skips_nonexistent_projects(self, tmp_path: Path) -> None:
        config = AppConfig(
            projects={"ghost": Path("/nonexistent/path")},
            index_path=tmp_path / ".doc-index.json",
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index = build_index(config)
        assert len(index.documents) == 0

    def test_multiple_projects(self, tmp_path: Path) -> None:
        proj_a = tmp_path / "a"
        proj_a.mkdir()
        (proj_a / "doc.md").write_text("A")

        proj_b = tmp_path / "b"
        proj_b.mkdir()
        (proj_b / "doc.md").write_text("B")

        config = AppConfig(
            projects={"a": proj_a, "b": proj_b},
            index_path=tmp_path / ".doc-index.json",
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index = build_index(config)
        assert len(index.documents) == 2
        assert "a::doc.md" in index.documents
        assert "b::doc.md" in index.documents


class TestReindex:
    def test_fresh_reindex_no_existing(self, fake_project: Path, sample_config: AppConfig) -> None:
        index, stats = reindex(sample_config)
        assert stats.new == 5
        assert stats.removed == 0
        assert stats.scanned == 5

    def test_reindex_detects_new_files(self, fake_project: Path, sample_config: AppConfig) -> None:
        index, _ = reindex(sample_config)

        # Add a new file
        (fake_project / "new.md").write_text("New doc")

        index2, stats = reindex(sample_config, existing=index)
        assert stats.new == 1
        assert "my-project::new.md" in index2.documents

    def test_reindex_detects_missing_file_as_desync(
        self, fake_project: Path, sample_config: AppConfig
    ) -> None:
        index, _ = reindex(sample_config)

        # Remove a file — should be desync, not removed
        (fake_project / "README.md").unlink()

        index2, stats = reindex(sample_config, existing=index)
        assert stats.desync == 1
        assert stats.removed == 0
        # Card preserved
        assert "my-project::README.md" in index2.documents

    def test_reindex_detects_changed_files(
        self, fake_project: Path, sample_config: AppConfig
    ) -> None:
        index, _ = reindex(sample_config)

        # Enrich a card first
        card = index.documents["my-project::README.md"]
        card.type = "project_doc"
        card.summary = "Main readme"
        card.enriched_at = datetime(2026, 3, 5, tzinfo=UTC)

        # Modify the file
        (fake_project / "README.md").write_text("# Changed content")

        index2, stats = reindex(sample_config, existing=index)
        assert stats.stale >= 1
        # Enrichment preserved
        changed = index2.documents["my-project::README.md"]
        assert changed.type == "project_doc"
        assert changed.summary == "Main readme"

    def test_reindex_preserves_unchanged(
        self, fake_project: Path, sample_config: AppConfig
    ) -> None:
        index, _ = reindex(sample_config)
        index2, stats = reindex(sample_config, existing=index)
        assert stats.unchanged == 5
        assert stats.new == 0
        assert stats.removed == 0


class TestUpdateCard:
    def test_update_type_and_summary(self) -> None:
        card = DocCard(
            project="proj",
            filename="doc.md",
            rel_path="doc.md",
            size=100,
            modified=datetime(2026, 3, 6, tzinfo=UTC),
            content_hash="abc",
        )
        index = IndexData(
            indexed_at=datetime(2026, 3, 6, tzinfo=UTC),
            documents={card.doc_id: card},
        )

        updated = update_card(index, "proj::doc.md", type="spec", summary="A spec")
        assert updated.type == "spec"
        assert updated.summary == "A spec"
        assert updated.enriched_at is not None

    def test_partial_update(self) -> None:
        card = DocCard(
            project="proj",
            filename="doc.md",
            rel_path="doc.md",
            size=100,
            modified=datetime(2026, 3, 6, tzinfo=UTC),
            content_hash="abc",
            type="reference",
            summary="Old summary",
        )
        index = IndexData(
            indexed_at=datetime(2026, 3, 6, tzinfo=UTC),
            documents={card.doc_id: card},
        )

        updated = update_card(index, "proj::doc.md", keywords=["api", "mcp"])
        assert updated.type == "reference"  # unchanged
        assert updated.summary == "Old summary"  # unchanged
        assert updated.keywords == ["api", "mcp"]  # updated

    def test_update_nonexistent_raises(self) -> None:
        index = IndexData(indexed_at=datetime(2026, 3, 6, tzinfo=UTC))
        with pytest.raises(KeyError, match="ghost::doc.md"):
            update_card(index, "ghost::doc.md", type="spec")


class TestPassthrough:
    def test_foreign_project_cards_preserved(self, tmp_path: Path) -> None:
        """Cards from projects not in config survive reindex."""
        proj_a = tmp_path / "a"
        proj_a.mkdir()
        (proj_a / "doc.md").write_text("A")

        config = AppConfig(
            projects={"a": proj_a},
            index_path=tmp_path / ".doc-index.json",
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )

        # Existing index has cards from projects a and b
        foreign_card = DocCard(
            project="b",
            filename="foreign.md",
            rel_path="foreign.md",
            size=50,
            modified=datetime(2026, 3, 5, tzinfo=UTC),
            content_hash="xyz",
            type="spec",
            summary="Foreign doc",
            enriched_at=datetime(2026, 3, 5, tzinfo=UTC),
        )
        index, _ = reindex(config)
        index.documents[foreign_card.doc_id] = foreign_card

        # Reindex with only project a in config
        index2, stats = reindex(config, existing=index)
        assert stats.passthrough == 1
        assert "b::foreign.md" in index2.documents
        # Enrichment preserved
        assert index2.documents["b::foreign.md"].type == "spec"
        assert index2.documents["b::foreign.md"].summary == "Foreign doc"

    def test_removed_file_from_configured_project_is_desync(self, tmp_path: Path) -> None:
        """Missing file from configured project = desync, not removed."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_path=tmp_path / ".doc-index.json",
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        # Delete the file
        (proj / "doc.md").unlink()

        index2, stats = reindex(config, existing=index)
        assert stats.desync == 1
        assert stats.removed == 0
        assert "proj::doc.md" in index2.documents


class TestDesync:
    def test_enriched_at_greater_than_modified_is_desync(self, tmp_path: Path) -> None:
        """Card enriched on another machine (enriched_at > modified) = desync."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_path=tmp_path / ".doc-index.json",
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        # Simulate enrichment from another machine (far future)
        card = index.documents["proj::doc.md"]
        card.enriched_at = datetime(2099, 1, 1, tzinfo=UTC)

        index2, stats = reindex(config, existing=index)
        assert stats.desync == 1
        assert stats.unchanged == 1  # card is still unchanged
        assert "proj::doc.md" in index2.documents


class TestForceReindex:
    def test_force_resets_enrichment(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_path=tmp_path / ".doc-index.json",
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)
        card = index.documents["proj::doc.md"]
        card.type = "spec"
        card.summary = "A spec"
        card.enriched_at = datetime(2026, 3, 5, tzinfo=UTC)

        index2, stats = reindex(config, existing=index, force=True)
        assert stats.new == 1
        new_card = index2.documents["proj::doc.md"]
        assert new_card.type is None
        assert new_card.summary is None
        assert new_card.enriched_at is None

    def test_force_preserves_foreign_cards(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_path=tmp_path / ".doc-index.json",
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        # Add foreign card
        foreign = DocCard(
            project="other",
            filename="f.md",
            rel_path="f.md",
            size=10,
            modified=datetime(2026, 3, 5, tzinfo=UTC),
            content_hash="abc",
            type="guide",
            enriched_at=datetime(2026, 3, 5, tzinfo=UTC),
        )
        index.documents[foreign.doc_id] = foreign

        index2, stats = reindex(config, existing=index, force=True)
        assert stats.passthrough == 1
        assert "other::f.md" in index2.documents
        assert index2.documents["other::f.md"].type == "guide"

    def test_force_removes_desync_cards(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_path=tmp_path / ".doc-index.json",
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        # Delete file — will be desync without force, removed with force
        (proj / "doc.md").unlink()

        index2, stats = reindex(config, existing=index, force=True)
        assert stats.removed == 1
        assert "proj::doc.md" not in index2.documents

    def test_default_force_false_backward_compatible(
        self, fake_project: Path, sample_config: AppConfig
    ) -> None:
        index, _ = reindex(sample_config)
        index2, stats = reindex(sample_config, existing=index)
        assert stats.unchanged == 5
        assert stats.new == 0
