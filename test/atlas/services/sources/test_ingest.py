"""Source ingestion (sources/ingest.py): the full ingest→search pipeline on
stubbed embeddings, plus scope semantics across multiple sources.
"""

from __future__ import annotations

import pytest

from atlas.services import sources
from atlas.services.sources import embeddings, extract


def make_pdf(path, page_texts: list[str]):
    """Write a real PDF with one page per entry."""
    import fitz

    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


# --- ingest pipeline (stubbed embeddings, real sqlite-vec) ------------------------

def test_ingest_pdf_end_to_end(tmp_path, stub_embeddings):
    pdf = tmp_path / "book.pdf"
    make_pdf(pdf, ["The Adam optimizer adapts step sizes.",
                   "Quokkas live on Rottnest Island."])
    record = sources.ingest_pdf(pdf, title="My Book")
    assert record["title"] == "My Book" and record["kind"] == "pdf"
    assert record["pages"] == 2 and record["n_chunks"] == 2

    hits = sources.search("Adam optimizer", top_k=1)
    assert hits and hits[0]["page"] == 1 and hits[0]["source_title"] == "My Book"


def test_add_source_requires_chunks(stub_embeddings):
    with pytest.raises(sources.SourceError, match="No text to index"):
        sources.add_source("Empty", "pdf", None, [(1, "   ")])


def test_add_source_embed_failure_raises(monkeypatch, stub_embeddings):
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts, **kw: None)
    with pytest.raises(sources.SourceError, match="Embedding failed"):
        sources.add_source("Book", "pdf", None, [(1, "real text")])


def test_ingest_url_uses_page_title(monkeypatch, stub_embeddings):
    # ingest_url calls extract.fetch_url, so stub it there.
    monkeypatch.setattr(extract, "fetch_url",
                        lambda url: ("Readable body text here.", "Fancy Page Title"))
    record = sources.ingest_url("https://x.test/page")
    assert record["title"] == "Fancy Page Title" and record["kind"] == "url"
    assert record["pages"] is None


# --- scope semantics across multiple sources --------------------------------------

@pytest.fixture()
def two_sources(stub_embeddings):
    optim = sources.add_source("Optim Book", "pdf", None, [(1, "the adam optimizer rules")])
    zoo = sources.add_source("Zoo Book", "pdf", None, [(1, "the adam quokka hops")])
    return optim["id"], zoo["id"]


def test_scope_none_searches_all(two_sources):
    titles = {hit["source_title"] for hit in sources.search("adam", top_k=10)}
    assert titles == {"Optim Book", "Zoo Book"}


def test_scope_subset_restricts(two_sources):
    a_id, _ = two_sources
    titles = {hit["source_title"] for hit in sources.search("adam", top_k=10, source_ids=[a_id])}
    assert titles == {"Optim Book"}


def test_scope_empty_searches_nothing(two_sources):
    assert sources.search("adam", top_k=10, source_ids=[]) == []


def test_list_and_delete_cascade(two_sources):
    a_id, b_id = two_sources
    assert {source["id"] for source in sources.list_sources()} == {a_id, b_id}
    assert sources.delete_source(a_id) is True
    assert {source["id"] for source in sources.list_sources()} == {b_id}
    # a's chunks are gone from retrieval entirely.
    titles = {hit["source_title"] for hit in sources.search("adam optimizer", top_k=10)}
    assert "Optim Book" not in titles
    assert sources.delete_source(a_id) is False  # already gone


def test_ingest_pdf_keeps_the_file_and_delete_removes_it(tmp_path, stub_embeddings):
    """The original PDF is kept beside the index (figures are mined from it
    later) and removed with the source."""
    from atlas.services.sources import store

    pdf = tmp_path / "kept.pdf"
    make_pdf(pdf, ["Some indexable text about optimizers."])
    record = sources.ingest_pdf(pdf, title="Kept")
    stored = store.pdf_path(record["id"])
    assert stored.exists() and stored.read_bytes().startswith(b"%PDF")

    assert sources.delete_source(record["id"]) is True
    assert not stored.exists()
