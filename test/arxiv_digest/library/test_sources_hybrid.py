"""Hybrid retrieval (Phase 3d.3): FTS5 lexical + vector KNN fused via RRF.

Offline — no embedding model, no network. The pure-function tests cover the
FTS5 query sanitizer and the RRF fusion; the integration test drives the real
``sources.search`` over a temp library with the vector side stubbed off, so it
exercises the lexical + fusion path end-to-end (triggers keep FTS5 in sync).
"""

from __future__ import annotations

import pytest

from arxiv_digest import config
from arxiv_digest.library import embeddings, sources


def test_fts_match_query_sanitizes() -> None:
    """Punctuation and FTS5 operators are neutralized to quoted OR'd tokens."""
    # A raw question with an apostrophe, math symbol, and the word "AND" — all
    # of which would trip the FTS5 grammar unquoted.
    assert sources._fts_match_query("Adam's β2 AND decay?") == (
        '"Adam" OR "s" OR "β2" OR "AND" OR "decay"'
    )
    # No usable tokens → empty (caller skips lexical search).
    assert sources._fts_match_query("   !!!   ") == ""


def test_rrf_fuse_rewards_agreement_and_dedupes() -> None:
    """A chunk ranked by both sides outranks one ranked highly by only one."""
    def chunk(cid: int) -> dict:
        return {"id": cid, "source_id": "s", "source_title": "T", "page": cid, "text": "x"}

    vector = [chunk(1), chunk(2), chunk(3)]   # 2 is #2 here
    lexical = [chunk(2), chunk(9)]            # 2 is #1 here → appears in both
    fused = sources._rrf_fuse([vector, lexical], k=10, rrf_k=60)

    ids = [h["page"] for h in fused]  # page mirrors id in this fixture
    assert ids[0] == 2                # in both lists → highest fused score
    assert ids.count(2) == 1          # deduplicated
    assert set(ids) == {1, 2, 3, 9}   # union of both rankings
    assert all("score" in h for h in fused)


def test_search_lexical_path_offline(monkeypatch, tmp_path) -> None:
    """search() returns FTS5 hits when the vector side is unavailable."""
    monkeypatch.setattr(config, "SOURCES_DB_PATH", tmp_path / "sources.db")
    # Force the semantic ranker off so only lexical + RRF run (no model load).
    monkeypatch.setattr(embeddings, "embed_query", lambda q: None)

    with sources._connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, title, kind, origin, pages, n_chunks) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("s1", "Deep Learning", "pdf", "dl.pdf", 10, 2),
        )
        conn.execute(
            "INSERT INTO chunks (source_id, page, text) VALUES (?, ?, ?)",
            ("s1", 42, "The Adam optimizer combines momentum with RMSProp."),
        )
        conn.execute(
            "INSERT INTO chunks (source_id, page, text) VALUES (?, ?, ?)",
            ("s1", 7, "Convolutional networks exploit spatial locality in images."),
        )

    if not sources._HAS_FTS:
        pytest.skip("FTS5 not compiled into this SQLite build")

    hits = sources.search("Adam optimizer", k=3)
    assert hits, "lexical search should find the Adam passage"
    assert hits[0]["source_title"] == "Deep Learning"
    assert hits[0]["page"] == 42
    assert "score" in hits[0]

    # An explicit empty scope still means "search nothing".
    assert sources.search("Adam optimizer", k=3, source_ids=[]) == []


def test_delete_source_purges_fts(monkeypatch, tmp_path) -> None:
    """Deleting a source drops its rows from the FTS5 index (via triggers)."""
    monkeypatch.setattr(config, "SOURCES_DB_PATH", tmp_path / "sources.db")
    monkeypatch.setattr(embeddings, "embed_query", lambda q: None)

    with sources._connect() as conn:
        conn.execute(
            "INSERT INTO sources (id, title, kind, origin, pages, n_chunks) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("s1", "Deep Learning", "pdf", "dl.pdf", 10, 1),
        )
        conn.execute(
            "INSERT INTO chunks (source_id, page, text) VALUES (?, ?, ?)",
            ("s1", 1, "The Adam optimizer is popular."),
        )

    if not sources._HAS_FTS:
        pytest.skip("FTS5 not compiled into this SQLite build")

    assert sources.search("Adam", k=3)
    assert sources.delete_source("s1") is True
    assert sources.search("Adam", k=3) == []
