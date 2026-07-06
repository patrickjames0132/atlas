"""Text extraction + chunking (sources/extract.py): chunk_text and extract_pdf.

Real PDFs are built in-memory with pymupdf — the same library ingestion uses —
so ``extract_pdf`` and the scanned-PDF rejection run against genuine documents,
offline.
"""

from __future__ import annotations

import pytest

from arxiv_digest.services import sources
from arxiv_digest.services.sources import extract

# --- chunk_text -----------------------------------------------------------------

def test_chunk_blank_and_short():
    assert extract.chunk_text("   \n\t ", 100, 20) == []
    assert extract.chunk_text("short text", 100, 20) == ["short text"]


def test_chunk_windows_overlap_and_break_on_spaces():
    words = " ".join(f"word{i:03d}" for i in range(200))  # ~1600 chars
    chunks = extract.chunk_text(words, size=300, overlap=60)
    assert len(chunks) > 3
    for chunk in chunks:
        assert len(chunk) <= 300
        assert not chunk.startswith(" ") and not chunk.endswith(" ")
        # Chunk ENDS break on a space — the last token is always intact.
        assert chunk.split()[-1] in words.split() or chunk is chunks[-1]
    # Nothing lost at the tail, and consecutive chunks overlap.
    assert chunks[-1].endswith("word199")
    assert chunks[1].split()[1] in chunks[0]


def test_chunk_collapses_whitespace():
    assert extract.chunk_text("a\n\nb\t\tc", 100, 10) == ["a b c"]


# --- extract_pdf (real in-memory PDFs) ------------------------------------------

def make_pdf(path, page_texts: list[str]):
    """Write a real PDF with one page per entry (empty string = blank page)."""
    import fitz

    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_extract_pdf_per_page_text(tmp_path):
    pdf = tmp_path / "doc.pdf"
    # Realistic page lengths — 3+ pages under 100 total chars would (rightly)
    # trip the scanned-PDF heuristic.
    make_pdf(pdf, ["Alpha " * 20, "", "Gamma " * 20])
    pages, total = extract.extract_pdf(pdf)
    assert total == 3
    assert [page for page, _ in pages] == [1, 3]  # blank page 2 dropped, numbering kept
    assert "Alpha" in pages[0][1]


def test_extract_pdf_rejects_scanned(tmp_path):
    pdf = tmp_path / "scan.pdf"
    make_pdf(pdf, ["", "", ""])  # 3 pages, no extractable text
    with pytest.raises(sources.SourceError, match="scanned"):
        extract.extract_pdf(pdf)
