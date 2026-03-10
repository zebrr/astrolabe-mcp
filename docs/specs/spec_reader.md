# spec_reader — File Reading

Status: READY

## Overview

Read file contents: full, by section heading (ATX), or by line range. Handles truncation for large files.

## Public API

### `read_file(file_path: Path, *, max_size_kb: int = 100, section: str | None = None, line_range: str | None = None) -> ReadResult`

Read a file's content with optional filtering.

**Parameters:**
- `file_path`: absolute path to the file
- `max_size_kb`: max size for full read (without section/range). If exceeded, content is truncated and `available_sections` is populated from full text headings.
- `section`: ATX heading text to extract (e.g. "Setup"). Returns content from that heading until the next heading of same or higher level.
- `line_range`: e.g. "1-50". 1-based inclusive.

**Priority:** `section` takes precedence over `line_range`. If both given, `section` wins.

**Returns:** `ReadResult` dataclass.

**Binary files:** If the file cannot be decoded as UTF-8 (e.g. images, audio, video), returns `ReadResult(content="[binary file]", total_lines=0, returned_lines=0)`. No error raised.

**Raises:**
- `FileNotFoundError` if file does not exist
- `ValueError` if line_range format is invalid

### `ReadResult` (dataclass)

```python
@dataclass
class ReadResult:
    content: str
    total_lines: int
    returned_lines: int
    section: str | None = None    # heading name if section was used
    truncated: bool = False       # True if content was truncated due to size limit
    available_sections: list[str] | None = None  # set when section not found OR when truncated
```

### `extract_headings(text: str) -> list[str]`

Extract all ATX headings from markdown text. Returns heading text without `#` prefix.

## Section Extraction Rules

- ATX headings only: `^#{1,6}\s+(.+)$`
- Section = from heading line to the line before the next heading of same or higher level (fewer or equal `#`)
- If section not found → `content=""`, `available_sections` populated
- Duplicate headings → first occurrence
- Case-sensitive match

## Dependencies

- `pathlib` (stdlib)
- `re` (stdlib)
