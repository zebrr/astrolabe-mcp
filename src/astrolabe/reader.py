"""File reading with section extraction and line ranges."""

import re
from dataclasses import dataclass, field
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class ReadResult:
    """Result of reading a file."""

    content: str
    total_lines: int
    returned_lines: int
    section: str | None = None
    truncated: bool = False
    available_sections: list[str] | None = field(default=None)


def extract_headings(text: str) -> list[str]:
    """Extract all ATX headings from markdown text."""
    return [m.group(2).strip() for m in HEADING_RE.finditer(text)]


def _extract_section(text: str, section: str) -> ReadResult:
    """Extract a section by heading name."""
    lines = text.splitlines(keepends=True)
    total = len(lines)

    # Find the heading
    target_level = 0
    start_idx = -1

    for i, line in enumerate(lines):
        m = HEADING_RE.match(line.rstrip("\n\r"))
        if m and m.group(2).strip() == section:
            target_level = len(m.group(1))
            start_idx = i
            break

    if start_idx == -1:
        return ReadResult(
            content="",
            total_lines=total,
            returned_lines=0,
            section=section,
            available_sections=extract_headings(text),
        )

    # Find the end: next heading of same or higher level
    end_idx = total
    for i in range(start_idx + 1, total):
        m = HEADING_RE.match(lines[i].rstrip("\n\r"))
        if m and len(m.group(1)) <= target_level:
            end_idx = i
            break

    section_lines = lines[start_idx:end_idx]
    return ReadResult(
        content="".join(section_lines),
        total_lines=total,
        returned_lines=len(section_lines),
        section=section,
    )


def _extract_range(text: str, line_range: str) -> ReadResult:
    """Extract lines by range (1-based inclusive)."""
    parts = line_range.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid line range format: {line_range!r}. Expected 'start-end'.")

    try:
        start = int(parts[0])
        end = int(parts[1])
    except ValueError:
        raise ValueError(
            f"Invalid line range format: {line_range!r}. Expected integers."
        ) from None

    if start < 1 or end < start:
        raise ValueError(f"Invalid line range: {line_range!r}. start must be >= 1 and <= end.")

    lines = text.splitlines(keepends=True)
    total = len(lines)
    selected = lines[start - 1 : end]

    return ReadResult(
        content="".join(selected),
        total_lines=total,
        returned_lines=len(selected),
    )


def read_file(
    file_path: Path,
    *,
    max_size_kb: int = 100,
    section: str | None = None,
    line_range: str | None = None,
) -> ReadResult:
    """Read a file's content with optional section or line range filtering.

    Args:
        file_path: Absolute path to the file.
        max_size_kb: Max file size in KB for full read without filters.
        section: ATX heading to extract.
        line_range: Line range like "1-50" (1-based inclusive).

    Returns:
        ReadResult with content and metadata.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        return ReadResult(
            content="[binary file]",
            total_lines=0,
            returned_lines=0,
        )

    if section is not None:
        return _extract_section(text, section)

    if line_range is not None:
        return _extract_range(text, line_range)

    # Full file read with size check
    lines = text.splitlines(keepends=True)
    total = len(lines)
    size_kb = file_path.stat().st_size / 1024

    if size_kb > max_size_kb:
        # Truncate to roughly max_size_kb
        truncated_text = text[: max_size_kb * 1024]
        truncated_lines = truncated_text.splitlines(keepends=True)
        return ReadResult(
            content="".join(truncated_lines),
            total_lines=total,
            returned_lines=len(truncated_lines),
            truncated=True,
            available_sections=extract_headings(text),
        )

    return ReadResult(
        content=text,
        total_lines=total,
        returned_lines=total,
    )
