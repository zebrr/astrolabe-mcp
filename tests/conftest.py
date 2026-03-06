"""Shared fixtures for astrolabe tests."""

from pathlib import Path

import pytest

from astrolabe.models import AppConfig


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """Create a minimal fake project with some docs."""
    proj = tmp_path / "my-project"
    proj.mkdir()

    # Root docs
    (proj / "README.md").write_text("# My Project\n\nSome content.")
    (proj / "CLAUDE.md").write_text("# CLAUDE.md\n\nInstructions here.")

    # Nested docs
    docs = proj / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\n## Setup\n\nSteps here.")
    (docs / "notes.txt").write_text("Some plain text notes.")
    (docs / "config.yaml").write_text("key: value\n")

    # Should be ignored
    git = proj / ".git"
    git.mkdir()
    (git / "config").write_text("git config")

    venv = proj / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("cfg")

    # Code (ignored by default config)
    src = proj / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')")

    return proj


@pytest.fixture
def sample_config(tmp_path: Path, fake_project: Path) -> AppConfig:
    """AppConfig pointing to the fake project."""
    return AppConfig(
        projects={"my-project": fake_project},
        index_path=tmp_path / ".doc-index.json",
        index_extensions=[".md", ".yaml", ".yml", ".txt"],
        ignore_dirs=[".git", ".venv", "src", "node_modules", "__pycache__"],
        ignore_files=["*.pyc", "*.lock"],
        max_file_size_kb=100,
    )
