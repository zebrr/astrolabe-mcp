"""File content chunking for embedding."""

import re
from pathlib import Path

MIN_CHUNK_SIZE = 20

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_text(
    text: str,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[str]:
    """Split text into overlapping chunks, paragraph-aware.

    Args:
        text: Text to chunk.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns:
        List of text chunks. Empty list if text is empty or too short.
    """
    text = text.strip()
    if len(text) < MIN_CHUNK_SIZE:
        return []

    # Single chunk if small enough
    if len(text) <= chunk_size:
        return [text]

    # Split by paragraphs (double newline)
    paragraphs = re.split(r"\n{2,}", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    # Break oversized paragraphs into sentences, then hard-split if needed
    fragments: list[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            fragments.append(para)
        else:
            # Split by sentences
            sentences = _SENTENCE_RE.split(para)
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(sent) <= chunk_size:
                    fragments.append(sent)
                else:
                    # Hard-split long sentences
                    for i in range(0, len(sent), chunk_size):
                        piece = sent[i : i + chunk_size]
                        if piece.strip():
                            fragments.append(piece.strip())

    # Reassemble fragments into chunks with overlap
    chunks: list[str] = []
    current = ""

    for frag in fragments:
        candidate = f"{current}\n\n{frag}" if current else frag
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            # Emit current chunk
            if current and len(current) >= MIN_CHUNK_SIZE:
                chunks.append(current)
            # Start new chunk with overlap from previous
            if current and chunk_overlap > 0:
                overlap_text = current[-chunk_overlap:]
                current = f"{overlap_text}\n\n{frag}" if overlap_text.strip() else frag
            else:
                current = frag

    # Emit last chunk
    if current and len(current) >= MIN_CHUNK_SIZE:
        chunks.append(current)

    return chunks


def chunk_file(
    file_path: Path,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    max_file_size_kb: int = 500,
) -> list[str]:
    """Split a file into overlapping text chunks for embedding.

    Args:
        file_path: Path to the file.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.
        max_file_size_kb: Skip files larger than this.

    Returns:
        List of text chunks. Empty list for binary files, oversized files, or empty files.
    """
    if not file_path.exists():
        return []

    # Check file size
    size = file_path.stat().st_size
    if size == 0:
        return []
    if size > max_file_size_kb * 1024:
        return []

    # Read as text
    try:
        text = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        return []  # binary file

    return chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
