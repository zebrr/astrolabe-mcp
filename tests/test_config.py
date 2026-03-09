"""Tests for astrolabe.config."""

import json
from pathlib import Path

import pytest

from astrolabe.config import load_config, load_doc_types, load_doc_types_full


class TestLoadConfig:
    def test_loads_valid_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "projects": {"proj": str(tmp_path / "proj")},
                    "index_dir": ".",
                    "index_extensions": [".md"],
                    "ignore_dirs": [".git"],
                    "ignore_files": ["*.pyc"],
                    "max_file_size_kb": 100,
                }
            )
        )

        config = load_config(config_file)
        assert config.projects["proj"] == tmp_path / "proj"
        assert config.max_file_size_kb == 100

    def test_index_dir_resolved_relative_to_config_dir(self, tmp_path: Path) -> None:
        config_file = tmp_path / "subdir" / "config.json"
        config_file.parent.mkdir()
        config_file.write_text(
            json.dumps(
                {
                    "projects": {},
                    "index_dir": ".",
                    "index_extensions": [],
                    "ignore_dirs": [],
                    "ignore_files": [],
                    "max_file_size_kb": 50,
                }
            )
        )

        config = load_config(config_file)
        assert config.index_dir == tmp_path / "subdir"

    def test_nonexistent_project_paths_kept(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "projects": {"ghost": "/nonexistent/path"},
                    "index_dir": ".",
                    "index_extensions": [],
                    "ignore_dirs": [],
                    "ignore_files": [],
                    "max_file_size_kb": 50,
                }
            )
        )

        config = load_config(config_file)
        assert "ghost" in config.projects

    def test_missing_config_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "missing.json")

    def test_invalid_config_raises_validation_error(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"projects": "not a dict"}))

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            load_config(config_file)

    def test_loads_config_example(self) -> None:
        """Smoke test: load the actual config.example.json."""
        example = Path(__file__).parent.parent / "config.example.json"
        if example.exists():
            config = load_config(example)
            assert config.max_file_size_kb == 100
            assert ".md" in config.index_extensions


class TestLoadConfigPrivate:
    def test_private_index_dir_resolved_relative(self, tmp_path: Path) -> None:
        config_file = tmp_path / "subdir" / "config.json"
        config_file.parent.mkdir()
        config_file.write_text(
            json.dumps(
                {
                    "projects": {"shared": str(tmp_path / "shared")},
                    "index_dir": ".",
                    "private_projects": {"secret": str(tmp_path / "secret")},
                    "private_index_dir": "private-idx",
                    "index_extensions": [".md"],
                    "ignore_dirs": [],
                    "ignore_files": [],
                    "max_file_size_kb": 50,
                }
            )
        )
        config = load_config(config_file)
        assert config.private_index_dir == tmp_path / "subdir" / "private-idx"

    def test_absolute_private_index_dir_unchanged(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "projects": {"shared": str(tmp_path / "shared")},
                    "index_dir": ".",
                    "private_projects": {"secret": str(tmp_path / "secret")},
                    "private_index_dir": "/absolute/path",
                    "index_extensions": [".md"],
                    "ignore_dirs": [],
                    "ignore_files": [],
                    "max_file_size_kb": 50,
                }
            )
        )
        config = load_config(config_file)
        assert config.private_index_dir == Path("/absolute/path")

    def test_no_private_fields_backward_compat(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "projects": {"a": str(tmp_path)},
                    "index_dir": ".",
                    "index_extensions": [".md"],
                    "ignore_dirs": [],
                    "ignore_files": [],
                    "max_file_size_kb": 50,
                }
            )
        )
        config = load_config(config_file)
        assert config.private_projects == {}
        assert config.private_index_dir is None


class TestLoadDocTypes:
    def test_loads_valid_doc_types(self, tmp_path: Path) -> None:
        dt_file = tmp_path / "doc_types.yaml"
        dt_file.write_text(
            "document_types:\n"
            "  instruction:\n"
            "    description: Project instruction\n"
            "  reference:\n"
            "    description: Reference material\n"
        )

        result = load_doc_types(dt_file)
        assert result["instruction"] == "Project instruction"
        assert result["reference"] == "Reference material"

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = load_doc_types(tmp_path / "missing.yaml")
        assert result == {}

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        dt_file = tmp_path / "doc_types.yaml"
        dt_file.write_text("")

        result = load_doc_types(dt_file)
        assert result == {}

    def test_no_document_types_key_returns_empty(self, tmp_path: Path) -> None:
        dt_file = tmp_path / "doc_types.yaml"
        dt_file.write_text("other_key: value\n")

        result = load_doc_types(dt_file)
        assert result == {}

    def test_strips_whitespace_from_descriptions(self, tmp_path: Path) -> None:
        dt_file = tmp_path / "doc_types.yaml"
        dt_file.write_text(
            "document_types:\n"
            "  skill:\n"
            "    description: >-\n"
            "      Agent skill with\n"
            "      multiple lines\n"
        )

        result = load_doc_types(dt_file)
        assert "Agent skill" in result["skill"]

    def test_loads_actual_doc_types(self) -> None:
        """Smoke test: load the actual doc_types.yaml."""
        actual = Path(__file__).parent.parent / "doc_types.yaml"
        if actual.exists():
            result = load_doc_types(actual)
            assert "instruction" in result
            assert "reference" in result
            assert len(result) >= 5


class TestLoadDocTypesFull:
    def test_returns_full_structure(self, tmp_path: Path) -> None:
        dt_file = tmp_path / "doc_types.yaml"
        dt_file.write_text(
            "document_types:\n"
            "  instruction:\n"
            "    description: Project instruction\n"
            "    examples:\n"
            "      - CLAUDE.md\n"
            "      - PROJECT.md\n"
            "  reference:\n"
            "    description: Reference material\n"
        )

        result = load_doc_types_full(dt_file)
        assert result["instruction"]["description"] == "Project instruction"
        assert result["instruction"]["examples"] == ["CLAUDE.md", "PROJECT.md"]
        assert result["reference"]["description"] == "Reference material"
        assert "examples" not in result["reference"]

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = load_doc_types_full(tmp_path / "missing.yaml")
        assert result == {}

    def test_missing_examples_omitted(self, tmp_path: Path) -> None:
        dt_file = tmp_path / "doc_types.yaml"
        dt_file.write_text("document_types:\n  spec:\n    description: Technical specification\n")

        result = load_doc_types_full(dt_file)
        assert "examples" not in result["spec"]
        assert result["spec"]["description"] == "Technical specification"

    def test_load_doc_types_is_consistent_wrapper(self, tmp_path: Path) -> None:
        """load_doc_types returns descriptions extracted from load_doc_types_full."""
        dt_file = tmp_path / "doc_types.yaml"
        dt_file.write_text(
            "document_types:\n"
            "  instruction:\n"
            "    description: Project instruction\n"
            "    examples:\n"
            "      - CLAUDE.md\n"
            "  reference:\n"
            "    description: Reference material\n"
        )

        full = load_doc_types_full(dt_file)
        flat = load_doc_types(dt_file)

        for name, entry in full.items():
            assert flat[name] == entry["description"]
