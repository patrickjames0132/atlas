"""Hybrid retrieval (sources/retrieval.py): FTS5 lexical + vector KNN fused via RRF.

Offline — no embedding model, no network. The pure-function tests cover the FTS5
query sanitizer and the RRF fusion; the integration tests drive the real
``sources.search`` over a temp library with the vector side stubbed off, so they
exercise the lexical + fusion path end-to-end (triggers keep FTS5 in sync).
"""

from __future__ import annotations

import pytest

from arxiv_digest.services import sources
from arxiv_digest.services.sources import embeddings, retrieval, store


def test_fts_match_query_sanitizes() -> None:
    """Punctuation and FTS5 operators are neutralized to quoted OR'd tokens."""
    # A raw question with an apostrophe, math symbol, and the word "AND" — all of
    # which would trip the FTS5 grammar unquoted.
    assert retrieval._fts_match_query("Adam's β2 AND decay?") == (
        '"Adam" OR "s" OR "β2" OR "AND" OR "decay"'
    )
    # No usable tokens → empty (caller skips lexical search).
    assert retrieval._fts_match_query("   !!!   ") == ""


def test_rrf_fuse_rewards_agreement_and_dedupes() -> None:
    """A chunk ranked by both sides outranks one ranked highly by only one."""
    def chunk(chunk_id: int) -> dict:
        return {"id": chunk_id, "source_id": "s", "source_title": "T",
                "page": chunk_id, "text": "x"}

    vector = [chunk(1), chunk(2), chunk(3)]   # 2 is #2 here
    lexical = [chunk(2), chunk(9)]            # 2 is #1 here → appears in both
    fused = retrieval._rrf_fuse([vector, lexical], k=10, rrf_k=60)

    ids = [hit["page"] for hit in fused]  # page mirrors id in this fixture
    assert ids[0] == 2                # in both lists → highest fused score
    assert ids.count(2) == 1          # deduplicated
    assert set(ids) == {1, 2, 3, 9}   # union of both rankings
    assert all("score" in hit for hit in fused)


def _seed_chunks(rows: list[tuple[int, str]], n_chunks: int) -> None:
    """Insert one source and its chunks straight into the store (FTS syncs via triggers)."""
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, title, kind, origin, pages, n_chunks) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("s1", "Deep Learning", "pdf", "dl.pdf", 10, n_chunks),
        )
        for page, text in rows:
            conn.execute(
                "INSERT INTO chunks (source_id, page, text) VALUES (?, ?, ?)",
                ("s1", page, text),
            )


def test_search_lexical_path_offline(monkeypatch) -> None:
    """search() returns FTS5 hits when the vector side is unavailable."""
    # Force the semantic ranker off so only lexical + RRF run (no model load).
    monkeypatch.setattr(embeddings, "embed_query", lambda q: None)
    _seed_chunks(
        [
            (42, "The Adam optimizer combines momentum with RMSProp."),
            (7, "Convolutional networks exploit spatial locality in images."),
        ],
        n_chunks=2,
    )
    if not store.HAS_FTS:
        pytest.skip("FTS5 not compiled into this SQLite build")

    hits = sources.search("Adam optimizer", k=3)
    assert hits, "lexical search should find the Adam passage"
    assert hits[0]["source_title"] == "Deep Learning"
    assert hits[0]["page"] == 42
    assert "score" in hits[0]

    # An explicit empty scope still means "search nothing".
    assert sources.search("Adam optimizer", k=3, source_ids=[]) == []


def test_delete_source_purges_fts(monkeypatch) -> None:
    """Deleting a source drops its rows from the FTS5 index (via triggers)."""
    monkeypatch.setattr(embeddings, "embed_query", lambda q: None)
    _seed_chunks([(1, "The Adam optimizer is popular.")], n_chunks=1)
    if not store.HAS_FTS:
        pytest.skip("FTS5 not compiled into this SQLite build")

    assert sources.search("Adam", k=3)
    assert sources.delete_source("s1") is True
    assert sources.search("Adam", k=3) == []
