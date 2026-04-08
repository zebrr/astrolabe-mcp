"""Tests for file content chunking."""

from pathlib import Path

from astrolabe.chunker import MIN_CHUNK_SIZE, chunk_file, chunk_text


class TestChunkText:
    """Tests for chunk_text()."""

    def test_empty_string(self) -> None:
        assert chunk_text("") == []

    def test_short_string(self) -> None:
        assert chunk_text("hi") == []
        assert chunk_text("x" * (MIN_CHUNK_SIZE - 1)) == []

    def test_minimum_size(self) -> None:
        text = "x" * MIN_CHUNK_SIZE
        result = chunk_text(text)
        assert result == [text]

    def test_single_chunk(self) -> None:
        text = "Hello world. This is a test document."
        result = chunk_text(text, chunk_size=800)
        assert len(result) == 1
        assert result[0] == text

    def test_multiple_paragraphs(self) -> None:
        para = "A" * 300
        text = f"{para}\n\n{para}\n\n{para}"
        result = chunk_text(text, chunk_size=400, chunk_overlap=50)
        assert len(result) >= 2
        # Each chunk should be <= chunk_size (approximately, overlap may push slightly)
        for chunk in result:
            assert len(chunk) >= MIN_CHUNK_SIZE

    def test_overlap_present(self) -> None:
        para1 = "Alpha beta gamma delta. " * 20  # ~480 chars
        para2 = "Epsilon zeta eta theta. " * 20
        text = f"{para1.strip()}\n\n{para2.strip()}"
        result = chunk_text(text, chunk_size=500, chunk_overlap=100)
        assert len(result) >= 2
        # Second chunk should contain some text from end of first
        if len(result) >= 2:
            tail_of_first = result[0][-50:]
            assert any(word in result[1] for word in tail_of_first.split()[:3])

    def test_oversized_paragraph_split_by_sentences(self) -> None:
        sentences = [f"Sentence number {i} is here." for i in range(30)]
        text = " ".join(sentences)  # one big paragraph
        result = chunk_text(text, chunk_size=200, chunk_overlap=30)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) >= MIN_CHUNK_SIZE

    def test_very_long_line_hard_split(self) -> None:
        text = "A" * 2000  # no sentences, no paragraphs
        result = chunk_text(text, chunk_size=500, chunk_overlap=50)
        assert len(result) >= 2
        for chunk in result:
            assert len(chunk) >= MIN_CHUNK_SIZE

    def test_whitespace_only_paragraphs_filtered(self) -> None:
        text = f"Content here.\n\n   \n\n{'More content. ' * 5}"
        result = chunk_text(text, chunk_size=800)
        assert len(result) >= 1
        for chunk in result:
            assert chunk.strip()

    def test_custom_sizes(self) -> None:
        text = "Word. " * 200
        result_small = chunk_text(text, chunk_size=100, chunk_overlap=20)
        result_large = chunk_text(text, chunk_size=1000, chunk_overlap=20)
        assert len(result_small) > len(result_large)


class TestChunkFile:
    """Tests for chunk_file()."""

    def test_text_file(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        content = "Hello world.\n\n" + "Some content. " * 50
        f.write_text(content, encoding="utf-8")
        result = chunk_file(f, chunk_size=200, chunk_overlap=30)
        assert len(result) >= 1

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.md"
        f.write_text("", encoding="utf-8")
        assert chunk_file(f) == []

    def test_binary_file(self, tmp_path: Path) -> None:
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\x00\x01\x02\xff\xfe\xfd" * 100)
        assert chunk_file(f) == []

    def test_oversized_file(self, tmp_path: Path) -> None:
        f = tmp_path / "huge.md"
        f.write_text("x" * 600_000, encoding="utf-8")
        assert chunk_file(f, max_file_size_kb=500) == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.md"
        assert chunk_file(f) == []

    def test_small_file_single_chunk(self, tmp_path: Path) -> None:
        f = tmp_path / "small.md"
        content = "A simple short document with enough text."
        f.write_text(content, encoding="utf-8")
        result = chunk_file(f, chunk_size=800)
        assert len(result) == 1
        assert result[0] == content

    def test_max_size_boundary(self, tmp_path: Path) -> None:
        f = tmp_path / "boundary.md"
        # Exactly at limit
        content = "x" * (50 * 1024)
        f.write_text(content, encoding="utf-8")
        result = chunk_file(f, max_file_size_kb=50)
        assert len(result) >= 1

        # Just over limit
        content_over = "x" * (50 * 1024 + 1)
        f.write_text(content_over, encoding="utf-8")
        assert chunk_file(f, max_file_size_kb=50) == []

    def test_utf8_content(self, tmp_path: Path) -> None:
        f = tmp_path / "russian.md"
        content = "Документация проекта.\n\n" + "Текст содержимого. " * 30
        f.write_text(content, encoding="utf-8")
        result = chunk_file(f, chunk_size=200, chunk_overlap=30)
        assert len(result) >= 1
        assert "Документация" in result[0]
