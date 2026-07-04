"""Source ingestion (library/sources.py): chunking, PDF extraction, the full
ingest→search pipeline (on stubbed embeddings), and scope semantics.

Real PDFs are built in-memory with pymupdf — the same library ingestion uses —
so ``extract_pdf`` and the scanned-PDF rejection run against genuine documents,
offline.
"""

from __future__ import annotations

import pytest
from arxiv_digest import config
from arxiv_digest.library import sources


# --- _chunk_text ----------------------------------------------------------------

def test_chunk_blank_and_short():
    assert sources._chunk_text("   \n\t ", 100, 20) == []
    assert sources._chunk_text("short text", 100, 20) == ["short text"]


def test_chunk_windows_overlap_and_break_on_spaces():
    words = " ".join(f"word{i:03d}" for i in range(200))  # ~1600 chars
    chunks = sources._chunk_text(words, size=300, overlap=60)
    assert len(chunks) > 3
    for c in chunks:
        assert len(c) <= 300
        assert not c.startswith(" ") and not c.endswith(" ")
        # Chunk ENDS break on a space — the last token is always intact.
        # (Starts may land mid-word: the overlap window rewinds by chars.)
        assert c.split()[-1] in words.split() or c is chunks[-1]
    # Nothing lost at the tail, and consecutive chunks overlap.
    assert chunks[-1].endswith("word199")
    assert chunks[1].split()[1] in chunks[0]


def test_chunk_collapses_whitespace():
    chunks = sources._chunk_text("a\n\nb\t\tc", 100, 10)
    assert chunks == ["a b c"]


# --- extract_pdf (real in-memory PDFs) -------------------------------------------

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
    pages, total = sources.extract_pdf(pdf)
    assert total == 3
    assert [p for p, _ in pages] == [1, 3]  # blank page 2 dropped, numbering kept
    assert "Alpha" in pages[0][1]


def test_extract_pdf_rejects_scanned(tmp_path):
    pdf = tmp_path / "scan.pdf"
    make_pdf(pdf, ["", "", ""])  # 3 pages, no extractable text
    with pytest.raises(sources.SourceError, match="scanned"):
        sources.extract_pdf(pdf)


# --- ingest pipeline (stubbed embeddings, real sqlite-vec) ------------------------

def test_ingest_pdf_end_to_end(tmp_path, stub_embeddings):
    pdf = tmp_path / "book.pdf"
    make_pdf(pdf, ["The Adam optimizer adapts step sizes.",
                   "Quokkas live on Rottnest Island."])
    record = sources.ingest_pdf(pdf, title="My Book")
    assert record["title"] == "My Book" and record["kind"] == "pdf"
    assert record["pages"] == 2 and record["n_chunks"] == 2

    hits = sources.search("Adam optimizer", k=1)
    assert hits and hits[0]["page"] == 1 and hits[0]["source_title"] == "My Book"


def test_add_source_requires_chunks(stub_embeddings):
    with pytest.raises(sources.SourceError, match="No text to index"):
        sources.add_source("Empty", "pdf", None, [(1, "   ")])


def test_add_source_embed_failure_raises(monkeypatch, stub_embeddings):
    from arxiv_digest.library import embeddings

    monkeypatch.setattr(embeddings, "embed_texts", lambda texts, **kw: None)
    with pytest.raises(sources.SourceError, match="Embedding failed"):
        sources.add_source("Book", "pdf", None, [(1, "real text")])


def test_ingest_url_uses_page_title(monkeypatch, stub_embeddings):
    monkeypatch.setattr(sources, "fetch_url",
                        lambda url: ("Readable body text here.", "Fancy Page Title"))
    record = sources.ingest_url("https://x.test/page")
    assert record["title"] == "Fancy Page Title" and record["kind"] == "url"
    assert record["pages"] is None


# --- scope semantics across multiple sources --------------------------------------

@pytest.fixture()
def two_sources(stub_embeddings):
    a = sources.add_source("Optim Book", "pdf", None, [(1, "the adam optimizer rules")])
    b = sources.add_source("Zoo Book", "pdf", None, [(1, "the adam quokka hops")])
    return a["id"], b["id"]


def test_scope_none_searches_all(two_sources):
    titles = {h["source_title"] for h in sources.search("adam", k=10)}
    assert titles == {"Optim Book", "Zoo Book"}


def test_scope_subset_restricts(two_sources):
    a_id, _ = two_sources
    titles = {h["source_title"] for h in sources.search("adam", k=10, source_ids=[a_id])}
    assert titles == {"Optim Book"}


def test_scope_empty_searches_nothing(two_sources):
    assert sources.search("adam", k=10, source_ids=[]) == []


def test_list_and_delete_cascade(two_sources):
    a_id, b_id = two_sources
    assert {s["id"] for s in sources.list_sources()} == {a_id, b_id}
    assert sources.delete_source(a_id) is True
    assert {s["id"] for s in sources.list_sources()} == {b_id}
    # a's chunks are gone from retrieval entirely.
    titles = {h["source_title"] for h in sources.search("adam optimizer", k=10)}
    assert "Optim Book" not in titles
    assert sources.delete_source(a_id) is False  # already gone
