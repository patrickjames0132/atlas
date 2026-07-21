"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Hybrid retrieval over the sources library: semantic KNN fused with lexical BM25.

Two rankers run over the same chunks — a semantic one (sqlite-vec cosine KNN over
the embeddings) and a lexical one (FTS5 BM25 over the raw text) — and their
results are combined with Reciprocal Rank Fusion, so both meaning and exact terms
count. See the package README for what FTS5 and RRF are and why we use both.

Everything degrades gracefully: with FTS5 missing (or hybrid off) it's pure
vector search; with the embedder missing it's lexical-only; with neither it
returns ``[]``.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import re
import sqlite3

from ...config import config
from . import embeddings, store

# FTS5 treats bare punctuation and words like AND/OR/NEAR as query syntax, so a
# raw question ("What's the Adam optimizer's β2?") can raise a parse error. We
# extract word tokens and OR them as quoted string literals — a safe, forgiving
# "any of these terms" match that never trips the grammar.
_FTS_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _fts_match_query(query: str) -> str:
    """Turn a free-text query into a safe FTS5 MATCH expression.

    Args:
        query: The user/agent's natural-language query.

    Returns:
        An ``"term1" OR "term2" ...`` string of quoted word tokens, or ``""``
        when the query has no usable tokens (caller then skips lexical search).
    """
    tokens = _FTS_TOKEN_RE.findall(query)
    return " OR ".join(f'"{token}"' for token in tokens)


def _scoped_where(ids: list[str], column: str) -> tuple[str, list[str]]:
    """Build an optional ``source_id IN (…)`` clause for a scoped search.

    Args:
        ids: The (already blank-filtered) source ids to restrict to; empty means
            no restriction.
        column: The qualified column to filter on, e.g. ``"c.source_id"``.

    Returns:
        A ``(clause, params)`` tuple — the clause is ``""`` (no restriction) or
        ``"AND <column> IN (?, …)"`` with matching ``params``.
    """
    if not ids:
        return "", []
    placeholders = ",".join("?" for _ in ids)
    return f"AND {column} IN ({placeholders})", list(ids)


def _vector_search(
    conn: sqlite3.Connection, query: str, fetch: int, ids: list[str]
) -> list[dict]:
    """Rank chunks by semantic similarity (sqlite-vec cosine KNN).

    Args:
        conn: An open library connection (sqlite-vec already loaded).
        query: The natural-language query to embed and match.
        fetch: How many candidates to pull (the RRF pool for this ranker).
        ids: Source-id scope (empty = whole library).

    Returns:
        Chunk dicts ``{id, source_id, source_title, page, text}`` best-first, or
        ``[]`` when the embedder or sqlite-vec is unavailable.
    """
    if not store.HAS_VEC:
        return []
    query_vector = embeddings.embed_query(query)
    if query_vector is None:
        return []

    import sqlite_vec

    scope, scope_params = _scoped_where(ids, "c.source_id")
    rows = conn.execute(
        f"""
        SELECT c.id, c.source_id, s.title AS source_title, c.page, c.text
        FROM (SELECT rowid, distance FROM chunks_vec
              WHERE embedding MATCH ? AND k = ?) knn
        JOIN chunks c ON c.id = knn.rowid
        JOIN sources s ON s.id = c.source_id
        WHERE 1 {scope}
        ORDER BY knn.distance
        """,
        [sqlite_vec.serialize_float32(query_vector), fetch, *scope_params],
    ).fetchall()
    return [dict(row) for row in rows]


def _lexical_search(
    conn: sqlite3.Connection, query: str, fetch: int, ids: list[str]
) -> list[dict]:
    """Rank chunks by lexical relevance (FTS5 BM25).

    Args:
        conn: An open library connection.
        query: The natural-language query (sanitized into an FTS5 expression).
        fetch: How many candidates to pull (the RRF pool for this ranker).
        ids: Source-id scope (empty = whole library).

    Returns:
        Chunk dicts ``{id, source_id, source_title, page, text}`` best-first, or
        ``[]`` when FTS5 is unavailable or the query has no usable terms.
    """
    if not store.HAS_FTS:
        return []
    match = _fts_match_query(query)
    if not match:
        return []
    scope, scope_params = _scoped_where(ids, "c.source_id")
    rows = conn.execute(
        f"""
        SELECT c.id, c.source_id, s.title AS source_title, c.page, c.text
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        JOIN sources s ON s.id = c.source_id
        WHERE chunks_fts MATCH ? {scope}
        ORDER BY bm25(chunks_fts)
        LIMIT ?
        """,
        [match, *scope_params, fetch],
    ).fetchall()
    return [dict(row) for row in rows]


def _rrf_fuse(rankings: list[list[dict]], top_k: int, rrf_k: int) -> list[dict]:
    """Fuse several ranked chunk lists via Reciprocal Rank Fusion.

    Each ranker contributes ``1 / (rrf_k + rank)`` (1-based rank) to a chunk's
    score, so a chunk ranked highly by *either* the semantic or the lexical side
    rises — no score normalization across the two scales needed.

    Args:
        rankings: One best-first list of chunk dicts per ranker; each dict must
            carry a unique ``id`` plus the display fields.
        top_k: Maximum fused passages to return.
        rrf_k: The RRF damping constant (larger flattens rank influence).

    Returns:
        Up to ``top_k`` passage dicts ``{source_id, source_title, page, text, score}``
        ordered by fused score (higher = stronger), deduplicated by chunk id.
    """
    scores: dict[int, float] = {}
    chunks: dict[int, dict] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            chunk_id = hit["id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            chunks.setdefault(chunk_id, hit)
    ordered = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)[:top_k]
    return [
        {
            "source_id": chunks[chunk_id]["source_id"],
            "source_title": chunks[chunk_id]["source_title"],
            "page": chunks[chunk_id]["page"],
            "text": chunks[chunk_id]["text"],
            "score": scores[chunk_id],
        }
        for chunk_id in ordered
    ]


def search(
    query: str, top_k: int | None = None, source_ids: list[str] | None = None
) -> list[dict]:
    """Hybrid search over the library — semantic KNN fused with lexical BM25.

    Runs a vector (sqlite-vec cosine KNN) and a lexical (FTS5 BM25) ranking and
    combines them with Reciprocal Rank Fusion, so both meaning and exact terms
    count. Degrades gracefully: with FTS5 missing (or hybrid off) it is pure
    vector search; with the embedder missing it is lexical-only; with neither it
    returns ``[]``.

    Args:
        query: What to look for — a concept or question.
        top_k: Maximum passages to return; defaults to ``config.sources.retrieval.search_k``.
        source_ids: Restrict retrieval to this subset of source ids. ``None``
            means "no scope" — search the whole library; an **explicit empty
            list** means "no sources selected" — search nothing (returns []).
            When filtering, each ranker's pool is over-fetched (8×) so the scope
            filter can still yield ``k`` hits from the chosen sources.

    Returns:
        Up to ``top_k`` passage dicts — ``{source_id, source_title, page, text,
        score}``, best-first (higher fused score = stronger). Empty when both
        rankers are unavailable, or when the scope is an explicit empty set.

    Raises:
        sqlite3.Error: On database failures.
    """
    top_k = top_k or config.sources.retrieval.search_k
    # None = whole library; an explicit (possibly empty) list = exactly those
    # sources, so an empty scope searches nothing rather than everything.
    if source_ids is not None:
        ids = [source_id for source_id in source_ids if source_id]
        if not ids:
            return []
    else:
        ids = []

    # Over-fetch each ranker when scoping so its pool still yields top_k in-scope
    # hits after the filter; also gives RRF a deeper pool to fuse over.
    fetch = top_k * 8 if ids else top_k

    with store.connect() as conn:
        vector = _vector_search(conn, query, fetch, ids)
        lexical = (
            _lexical_search(conn, query, fetch, ids)
            if config.sources.retrieval.hybrid
            else []
        )

    return _rrf_fuse([vector, lexical], top_k, config.sources.retrieval.rrf_k)
