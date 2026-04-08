# Spec: chunker.py

**Status**: READY

## Purpose

Split file content into overlapping text chunks for embedding. Pure utility module — no dependencies on other astrolabe modules.

## Public API

### `chunk_file(file_path, *, chunk_size=800, chunk_overlap=100, max_file_size_kb=500) -> list[str]`

Split a file into overlapping text chunks.

**Args:**
- `file_path: Path` — path to the file
- `chunk_size: int` — target chunk size in characters (default 800)
- `chunk_overlap: int` — overlap between consecutive chunks (default 100)
- `max_file_size_kb: int` — skip files larger than this (default 500)

**Returns:** list of text chunks. Empty list for binary files, oversized files, or empty files.

**Algorithm:**
1. Read file as UTF-8. If `UnicodeDecodeError` → return `[]` (binary file)
2. If file size > `max_file_size_kb * 1024` → return `[]`
3. Split by paragraphs (double newline `\n\n`)
4. Reassemble paragraphs into chunks of ~`chunk_size` characters with `chunk_overlap` overlap
5. If a single paragraph exceeds `chunk_size` → split by sentences (`. `, `! `, `? `), then hard-split if still too large
6. Skip chunks shorter than 20 characters

### `chunk_text(text, *, chunk_size=800, chunk_overlap=100) -> list[str]`

Chunk a text string directly (for testing and reuse).

**Args:**
- `text: str` — text to chunk
- `chunk_size: int` — target chunk size
- `chunk_overlap: int` — overlap

**Returns:** list of text chunks.

## Constants

```python
MIN_CHUNK_SIZE = 20  # skip tiny chunks
```

## Edge Cases

- Empty file → `[]`
- File smaller than chunk_size → single chunk (the entire content)
- Binary file (UnicodeDecodeError) → `[]`
- File exceeds max_file_size_kb → `[]`
- Text with no paragraph breaks → sentence-level splitting
- Single very long line → hard-split at chunk_size
