"""Tests for astrolabe.index."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from astrolabe import __version__
from astrolabe.index import (
    _compute_hash,
    _list_files_git,
    _list_files_rglob,
    build_hash_map,
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
            index_dir=tmp_path,
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
            index_dir=tmp_path,
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
            index_dir=tmp_path,
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
        assert updated.enriched_content_hash == "abc"

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
            index_dir=tmp_path,
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
            index_dir=tmp_path,
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
    def test_enriched_at_greater_than_modified_is_not_desync(self, tmp_path: Path) -> None:
        """enriched_at > modified is normal state, not desync."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        # Simulate enrichment (enriched_at > modified is normal)
        card = index.documents["proj::doc.md"]
        card.enriched_at = datetime(2099, 1, 1, tzinfo=UTC)
        card.enriched_content_hash = card.content_hash

        index2, stats = reindex(config, existing=index)
        assert stats.desync == 0  # not desync — file exists, hash matches
        assert stats.unchanged == 1
        assert "proj::doc.md" in index2.documents


class TestMigration:
    def test_enriched_card_without_enriched_content_hash_gets_migrated(
        self, tmp_path: Path
    ) -> None:
        """Old enriched cards (no enriched_content_hash) get it auto-set on reindex."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        # Simulate old-format enrichment (no enriched_content_hash)
        card = index.documents["proj::doc.md"]
        card.enriched_at = datetime(2026, 3, 5, tzinfo=UTC)
        card.type = "spec"
        card.summary = "A spec"
        assert card.enriched_content_hash is None

        index2, stats = reindex(config, existing=index)
        migrated = index2.documents["proj::doc.md"]
        assert migrated.enriched_content_hash == migrated.content_hash
        assert migrated.is_stale is False
        assert migrated.type == "spec"  # enrichment preserved


class TestReindexModes:
    def test_rebuild_resets_enrichment(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
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

        index2, stats = reindex(config, existing=index, mode="rebuild")
        assert stats.new == 1
        new_card = index2.documents["proj::doc.md"]
        assert new_card.type is None
        assert new_card.summary is None
        assert new_card.enriched_at is None

    def test_rebuild_preserves_foreign_cards(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
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

        index2, stats = reindex(config, existing=index, mode="rebuild")
        assert stats.passthrough == 1
        assert "other::f.md" in index2.documents
        assert index2.documents["other::f.md"].type == "guide"

    def test_rebuild_removes_desync_cards(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        # Delete file — will be desync in update, removed in rebuild
        (proj / "doc.md").unlink()

        index2, stats = reindex(config, existing=index, mode="rebuild")
        assert stats.removed == 1
        assert "proj::doc.md" not in index2.documents

    def test_clean_removes_desync_keeps_enrichment(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "a.md").write_text("content a")
        (proj / "b.md").write_text("content b")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        # Enrich both cards
        from astrolabe.index import update_card

        update_card(index, "proj::a.md", type="spec", summary="Spec A")
        update_card(index, "proj::b.md", type="guide", summary="Guide B")

        # Delete one file — only it should be removed, other keeps enrichment
        (proj / "b.md").unlink()

        index2, stats = reindex(config, existing=index, mode="clean")
        assert stats.removed == 1
        assert stats.unchanged == 1
        assert "proj::b.md" not in index2.documents
        # Enrichment preserved on surviving card
        assert index2.documents["proj::a.md"].type == "spec"
        assert index2.documents["proj::a.md"].summary == "Spec A"

    def test_clean_skips_move_detection(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)
        from astrolabe.index import update_card

        update_card(index, "proj::doc.md", type="spec", summary="Spec")

        (proj / "sub").mkdir()
        (proj / "doc.md").rename(proj / "sub" / "doc.md")

        _, stats = reindex(config, existing=index, mode="clean")
        assert len(stats.auto_transferred) == 0
        assert stats.removed == 1

    def test_default_mode_update(self, fake_project: Path, sample_config: AppConfig) -> None:
        index, _ = reindex(sample_config)
        index2, stats = reindex(sample_config, existing=index)
        assert stats.unchanged == 5
        assert stats.new == 0


class TestMoveDetection:
    def test_auto_transfer_on_rename(self, tmp_path: Path) -> None:
        """File moved to a new path: enrichment auto-transferred by content_hash."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "docs").mkdir()
        (proj / "docs" / "guide.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        from astrolabe.index import update_card

        update_card(
            index,
            "proj::docs/guide.md",
            type="reference",
            summary="A guide",
            keywords=["guide"],
        )

        # Move the file
        (proj / "archive").mkdir()
        (proj / "docs" / "guide.md").rename(proj / "archive" / "guide.md")

        index2, stats = reindex(config, existing=index)
        assert stats.desync == 0  # resolved by auto-transfer
        assert stats.new == 1
        assert len(stats.auto_transferred) == 1
        assert stats.auto_transferred[0] == ("proj::docs/guide.md", "proj::archive/guide.md")
        # Old card removed, new card has enrichment
        assert "proj::docs/guide.md" not in index2.documents
        new_card = index2.documents["proj::archive/guide.md"]
        assert new_card.type == "reference"
        assert new_card.summary == "A guide"
        assert new_card.keywords == ["guide"]
        assert new_card.enriched_at is not None
        assert not new_card.is_stale

    def test_batch_rename(self, tmp_path: Path) -> None:
        """Multiple files renamed at once: each auto-transferred independently."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "old").mkdir()
        for i in range(5):
            (proj / "old" / f"doc{i}.md").write_text(f"content-{i}")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        from astrolabe.index import update_card

        for i in range(5):
            update_card(
                index,
                f"proj::old/doc{i}.md",
                type="spec",
                summary=f"Doc {i}",
            )

        # Move all files
        (proj / "new").mkdir()
        for i in range(5):
            (proj / "old" / f"doc{i}.md").rename(proj / "new" / f"doc{i}.md")

        index2, stats = reindex(config, existing=index)
        assert len(stats.auto_transferred) == 5
        assert stats.desync == 0
        for i in range(5):
            new_card = index2.documents[f"proj::new/doc{i}.md"]
            assert new_card.type == "spec"
            assert new_card.summary == f"Doc {i}"

    def test_move_to_different_dir(self, tmp_path: Path) -> None:
        """File moved to a different folder: hash matches, auto-transfer."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        from astrolabe.index import update_card

        update_card(index, "proj::doc.md", type="spec", summary="Spec")

        (proj / "sub").mkdir()
        (proj / "doc.md").rename(proj / "sub" / "doc.md")

        index2, stats = reindex(config, existing=index)
        assert len(stats.auto_transferred) == 1
        assert stats.desync == 0
        assert "proj::doc.md" not in index2.documents
        assert index2.documents["proj::sub/doc.md"].type == "spec"

    def test_ambiguous_move(self, tmp_path: Path) -> None:
        """Two desync cards with same hash + one new card: ambiguous."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "a").mkdir()
        (proj / "a" / "copy1.md").write_text("same content")
        (proj / "a" / "copy2.md").write_text("same content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        from astrolabe.index import update_card

        update_card(index, "proj::a/copy1.md", type="spec", summary="Copy 1")
        update_card(index, "proj::a/copy2.md", type="spec", summary="Copy 2")

        # Delete both, create one new file with same content
        (proj / "a" / "copy1.md").unlink()
        (proj / "a" / "copy2.md").unlink()
        (proj / "b").mkdir()
        (proj / "b" / "merged.md").write_text("same content")

        _, stats = reindex(config, existing=index)
        assert len(stats.auto_transferred) == 0
        assert len(stats.ambiguous_moves) == 1
        entry = stats.ambiguous_moves[0]
        assert set(entry["desync_ids"]) == {"proj::a/copy1.md", "proj::a/copy2.md"}
        assert entry["new_ids"] == ["proj::b/merged.md"]

    def test_no_transfer_if_content_changed(self, tmp_path: Path) -> None:
        """File renamed AND modified: hash differs, no match."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("original")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)

        from astrolabe.index import update_card

        update_card(index, "proj::doc.md", type="spec", summary="Spec")

        # Rename AND change content
        (proj / "doc.md").unlink()
        (proj / "renamed.md").write_text("modified content")

        index2, stats = reindex(config, existing=index)
        assert len(stats.auto_transferred) == 0
        assert len(stats.ambiguous_moves) == 0
        assert stats.desync == 1
        assert index2.documents["proj::renamed.md"].is_empty

    def test_no_transfer_if_unenriched(self, tmp_path: Path) -> None:
        """Only enriched desync cards are candidates for move detection."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)
        # Don't enrich — card is empty

        (proj / "sub").mkdir()
        (proj / "doc.md").rename(proj / "sub" / "doc.md")

        _, stats = reindex(config, existing=index)
        assert len(stats.auto_transferred) == 0

    def test_no_transfer_on_rebuild(self, tmp_path: Path) -> None:
        """Rebuild mode skips move detection."""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "doc.md").write_text("content")

        config = AppConfig(
            projects={"proj": proj},
            index_dir=tmp_path,
            index_extensions=[".md"],
            ignore_dirs=[],
            ignore_files=[],
            max_file_size_kb=100,
        )
        index, _ = reindex(config)
        from astrolabe.index import update_card

        update_card(index, "proj::doc.md", type="spec", summary="Spec")

        (proj / "sub").mkdir()
        (proj / "doc.md").rename(proj / "sub" / "doc.md")

        _, stats = reindex(config, existing=index, mode="rebuild")
        assert len(stats.auto_transferred) == 0


class TestGitAwareScan:
    """Tests for git-aware file discovery in scan_project."""

    def test_excludes_gitignored(self, fake_git_project: Path, git_config: AppConfig) -> None:
        """Gitignored files (.venv/, __pycache__/) should not appear."""
        cards = scan_project("my-git-project", fake_git_project, git_config)
        paths = {c.rel_path for c in cards}
        assert not any(".venv" in p for p in paths)
        assert not any("__pycache__" in p for p in paths)
        assert not any(".pyc" in p for p in paths)

    def test_includes_untracked_not_ignored(
        self, fake_git_project: Path, git_config: AppConfig
    ) -> None:
        """Untracked files not matching .gitignore should appear."""
        cards = scan_project("my-git-project", fake_git_project, git_config)
        filenames = {c.filename for c in cards}
        assert "untracked.md" in filenames

    def test_still_applies_ignore_dirs(
        self, fake_git_project: Path, git_config: AppConfig
    ) -> None:
        """src/ is tracked by git but excluded by astrolabe ignore_dirs."""
        cards = scan_project("my-git-project", fake_git_project, git_config)
        paths = {c.rel_path for c in cards}
        assert not any("src/" in p for p in paths)

    def test_still_applies_index_extensions(
        self, fake_git_project: Path, git_config: AppConfig
    ) -> None:
        """Only files with configured extensions pass."""
        cards = scan_project("my-git-project", fake_git_project, git_config)
        for card in cards:
            assert Path(card.filename).suffix in git_config.index_extensions

    def test_finds_committed_docs(self, fake_git_project: Path, git_config: AppConfig) -> None:
        """Committed .md files should be found."""
        cards = scan_project("my-git-project", fake_git_project, git_config)
        filenames = {c.filename for c in cards}
        assert "README.md" in filenames
        assert "guide.md" in filenames

    def test_fallback_non_git(self, fake_project: Path, sample_config: AppConfig) -> None:
        """Non-git directory falls back to rglob."""
        cards = scan_project("my-project", fake_project, sample_config)
        filenames = {c.filename for c in cards}
        # Should still find files via rglob fallback
        assert "README.md" in filenames
        assert len(cards) == 5

    def test_fallback_git_not_installed(
        self, fake_git_project: Path, git_config: AppConfig
    ) -> None:
        """When git is not installed, falls back to rglob."""
        with patch("astrolabe.index.subprocess.run", side_effect=FileNotFoundError):
            cards = scan_project("my-git-project", fake_git_project, git_config)
        # Should still find files via rglob fallback
        filenames = {c.filename for c in cards}
        assert "README.md" in filenames


class TestBuildHashMap:
    def test_no_duplicates_returns_empty(self) -> None:
        cards = {
            "a::doc.md": DocCard(
                project="a",
                filename="doc.md",
                rel_path="doc.md",
                size=10,
                modified=datetime(2026, 3, 6, tzinfo=UTC),
                content_hash="aaa",
            ),
            "b::doc.md": DocCard(
                project="b",
                filename="doc.md",
                rel_path="doc.md",
                size=10,
                modified=datetime(2026, 3, 6, tzinfo=UTC),
                content_hash="bbb",
            ),
        }
        assert build_hash_map(cards) == {}

    def test_duplicates_returned(self) -> None:
        cards = {
            "a::doc.md": DocCard(
                project="a",
                filename="doc.md",
                rel_path="doc.md",
                size=10,
                modified=datetime(2026, 3, 6, tzinfo=UTC),
                content_hash="same",
            ),
            "b::doc.md": DocCard(
                project="b",
                filename="doc.md",
                rel_path="doc.md",
                size=10,
                modified=datetime(2026, 3, 6, tzinfo=UTC),
                content_hash="same",
            ),
            "c::other.md": DocCard(
                project="c",
                filename="other.md",
                rel_path="other.md",
                size=10,
                modified=datetime(2026, 3, 6, tzinfo=UTC),
                content_hash="unique",
            ),
        }
        result = build_hash_map(cards)
        assert "same" in result
        assert set(result["same"]) == {"a::doc.md", "b::doc.md"}
        assert "unique" not in result

    def test_empty_index(self) -> None:
        assert build_hash_map({}) == {}

    def test_three_way_duplicate(self) -> None:
        cards = {
            f"{p}::doc.md": DocCard(
                project=p,
                filename="doc.md",
                rel_path="doc.md",
                size=10,
                modified=datetime(2026, 3, 6, tzinfo=UTC),
                content_hash="same",
            )
            for p in ("a", "b", "c")
        }
        result = build_hash_map(cards)
        assert len(result["same"]) == 3


class TestListFilesGit:
    """Unit tests for _list_files_git helper."""

    def test_returns_paths_for_git_repo(self, fake_git_project: Path) -> None:
        result = _list_files_git(fake_git_project)
        assert result is not None
        assert len(result) > 0
        # All should be absolute paths
        for p in result:
            assert p.is_absolute()

    def test_returns_none_for_non_git(self, tmp_path: Path) -> None:
        result = _list_files_git(tmp_path)
        assert result is None

    def test_returns_none_when_git_missing(self, fake_git_project: Path) -> None:
        with patch("astrolabe.index.subprocess.run", side_effect=FileNotFoundError):
            result = _list_files_git(fake_git_project)
        assert result is None

    def test_excludes_gitignored_files(self, fake_git_project: Path) -> None:
        result = _list_files_git(fake_git_project)
        assert result is not None
        names = {p.name for p in result}
        assert "pyvenv.cfg" not in names
        assert "mod.cpython-311.pyc" not in names

    def test_includes_untracked_non_ignored(self, fake_git_project: Path) -> None:
        result = _list_files_git(fake_git_project)
        assert result is not None
        names = {p.name for p in result}
        assert "untracked.md" in names


class TestListFilesRglob:
    """Unit tests for _list_files_rglob helper."""

    def test_lists_all_files(self, fake_project: Path) -> None:
        result = _list_files_rglob(fake_project)
        assert len(result) > 0
        for p in result:
            assert p.is_file()

    def test_excludes_symlinks(self, tmp_path: Path) -> None:
        (tmp_path / "real.md").write_text("content")
        (tmp_path / "link.md").symlink_to(tmp_path / "real.md")
        result = _list_files_rglob(tmp_path)
        names = {p.name for p in result}
        assert "real.md" in names
        assert "link.md" not in names
