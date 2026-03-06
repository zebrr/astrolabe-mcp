"""Tests for astrolabe.reader."""

from pathlib import Path

import pytest

from astrolabe.reader import extract_headings, read_file

SAMPLE_MD = """\
# Title

Introduction paragraph.

## Setup

Setup instructions here.

### Prerequisites

You need Python 3.11+.

## Usage

Usage instructions here.

## FAQ

Frequently asked questions.
"""


class TestExtractHeadings:
    def test_extracts_all_levels(self) -> None:
        headings = extract_headings(SAMPLE_MD)
        assert headings == ["Title", "Setup", "Prerequisites", "Usage", "FAQ"]

    def test_empty_text(self) -> None:
        assert extract_headings("") == []

    def test_no_headings(self) -> None:
        assert extract_headings("Just plain text.\nNo headings here.") == []


class TestReadFileSection:
    def test_extract_section(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(SAMPLE_MD)

        result = read_file(f, section="Setup")
        assert "Setup instructions here." in result.content
        assert "Prerequisites" in result.content  # subsection included
        assert result.section == "Setup"
        assert result.returned_lines > 0

    def test_section_stops_at_same_level(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(SAMPLE_MD)

        result = read_file(f, section="Setup")
        assert "Usage instructions" not in result.content

    def test_section_not_found(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(SAMPLE_MD)

        result = read_file(f, section="Nonexistent")
        assert result.content == ""
        assert result.available_sections is not None
        assert "Setup" in result.available_sections

    def test_last_section(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(SAMPLE_MD)

        result = read_file(f, section="FAQ")
        assert "Frequently asked questions." in result.content


class TestReadFileRange:
    def test_line_range(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("line1\nline2\nline3\nline4\nline5\n")

        result = read_file(f, line_range="2-4")
        assert "line2" in result.content
        assert "line4" in result.content
        assert "line1" not in result.content
        assert "line5" not in result.content
        assert result.returned_lines == 3

    def test_invalid_range_format(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("content")

        with pytest.raises(ValueError, match="Invalid line range"):
            read_file(f, line_range="abc")

    def test_invalid_range_values(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("content")

        with pytest.raises(ValueError, match="Invalid line range"):
            read_file(f, line_range="5-2")


class TestReadFileFull:
    def test_full_read(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(SAMPLE_MD)

        result = read_file(f)
        assert result.content == SAMPLE_MD
        assert result.truncated is False
        assert result.total_lines == result.returned_lines

    def test_truncation(self, tmp_path: Path) -> None:
        f = tmp_path / "big.md"
        # Write ~2KB file, set max to 1KB
        f.write_text("x" * 2048)

        result = read_file(f, max_size_kb=1)
        assert result.truncated is True
        assert len(result.content) <= 1024

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_file(tmp_path / "missing.md")

    def test_binary_file(self, tmp_path: Path) -> None:
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        result = read_file(f)
        assert result.content == "[binary file]"
        assert result.total_lines == 0
        assert result.returned_lines == 0

    def test_section_takes_precedence_over_range(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(SAMPLE_MD)

        result = read_file(f, section="Setup", line_range="1-2")
        assert result.section == "Setup"
        assert "Setup instructions" in result.content
