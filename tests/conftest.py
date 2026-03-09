"""Shared fixtures for astrolabe tests."""

import subprocess
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
        index_dir=tmp_path,
        index_extensions=[".md", ".yaml", ".yml", ".txt"],
        ignore_dirs=[".git", ".venv", "src", "node_modules", "__pycache__"],
        ignore_files=["*.pyc", "*.lock"],
        max_file_size_kb=100,
    )


def _git(cwd: Path, *args: str) -> None:
    """Run a git command in the given directory."""
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        check=True,
        env={
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
            "HOME": str(cwd),
            "PATH": "/usr/bin:/usr/local/bin:/opt/homebrew/bin",
        },
    )


@pytest.fixture
def fake_git_project(tmp_path: Path) -> Path:
    """Create a fake project that is a git repository.

    Structure:
        my-git-project/
        ├── README.md          (committed)
        ├── docs/
        │   └── guide.md       (committed)
        ├── src/
        │   └── main.py        (committed, but excluded by astrolabe ignore_dirs)
        ├── untracked.md       (untracked, not ignored → should appear)
        ├── .gitignore         (committed)
        ├── .venv/
        │   └── pyvenv.cfg     (gitignored → should NOT appear)
        └── __pycache__/
            └── mod.cpython-311.pyc  (gitignored → should NOT appear)
    """
    proj = tmp_path / "my-git-project"
    proj.mkdir()

    _git(proj, "init")

    # .gitignore
    (proj / ".gitignore").write_text(".venv/\n__pycache__/\n*.pyc\n")

    # Committed files
    (proj / "README.md").write_text("# My Git Project\n\nSome content.")
    docs = proj / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n\n## Setup\n\nSteps here.")
    src = proj / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')")

    _git(proj, "add", ".")
    _git(proj, "commit", "-m", "initial")

    # Gitignored files (created AFTER commit to avoid accidental staging)
    venv = proj / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("cfg")
    pycache = proj / "__pycache__"
    pycache.mkdir()
    (pycache / "mod.cpython-311.pyc").write_bytes(b"\x00\x00")

    # Untracked but not ignored
    (proj / "untracked.md").write_text("Untracked doc")

    return proj


@pytest.fixture
def git_config(tmp_path: Path, fake_git_project: Path) -> AppConfig:
    """AppConfig for git-aware project with cleaned-up ignore_dirs."""
    return AppConfig(
        projects={"my-git-project": fake_git_project},
        index_dir=tmp_path,
        index_extensions=[".md", ".yaml", ".yml", ".txt"],
        ignore_dirs=["src", "lib", "app", "tests", "test"],
        ignore_files=["*.lock"],
        max_file_size_kb=100,
    )
