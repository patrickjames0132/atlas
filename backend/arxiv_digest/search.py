"""Search orchestration: hybrid lexical + semantic retrieval.

`hybrid_search` runs the lexical index (FTS5/BM25) and the semantic index
(sqlite-vec KNN over embeddings) independently, then blends the two ranked lists
with Reciprocal Rank Fusion (RRF). RRF needs only each result's *rank* in its
list — not comparable scores — so it fairly combines BM25 (word statistics) with
cosine distance (embedding similarity), and a paper found near the top of both
lists rises above one that only one method liked.

Degrades to lexical-only when embeddings aren't available (model didn't load or
ARXIV_SEMANTIC=0), so callers always get results.
"""

from __future__ import annotations

from typing import Optional

from . import arxiv_client, config, embeddings, store


def _rrf_scores(ranked_ids: list[list[str]], k: int) -> dict[str, float]:
    """Reciprocal Rank Fusion: score = Σ 1 / (k + rank) over each list a doc
    appears in (rank is 1-based). Higher = better."""
    scores: dict[str, float] = {}
    for ids in ranked_ids:
        for rank, arxiv_id in enumerate(ids, start=1):
            scores[arxiv_id] = scores.get(arxiv_id, 0.0) + 1.0 / (k + rank)
    return scores


def hybrid_search(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
) -> tuple[list[dict], str]:
    """Return (papers, mode). ``mode`` is "hybrid" when both indexes ran, else
    "lexical". Papers are ordered by fused relevance; each carries a ``matched_by``
    list noting which index(es) surfaced it."""
    q = (query or "").strip()
    if not q:
        return [], "lexical"

    # Lexical side (always available; FTS5 or LIKE fallback inside the store).
    lexical = store.search_papers(q, start_date, end_date, limit=max(limit, 100))

    # Semantic side (best-effort).
    semantic: list[dict] = []
    query_vec = None
    if store.has_vectors() and embeddings.available():
        query_vec = embeddings.embed_query(q)
    if query_vec is not None:
        semantic = store.semantic_search(
            query_vec, start_date, end_date, limit=max(limit, 100)
        )

    if not semantic:
        # Lexical-only: keep BM25 order, trim to limit.
        for p in lexical:
            p["matched_by"] = ["lexical"]
        return lexical[:limit], "lexical"

    # Merge: build one id→paper map and record which list(s) each id came from.
    by_id: dict[str, dict] = {}
    lex_ids = [p["arxiv_id"] for p in lexical]
    sem_ids = [p["arxiv_id"] for p in semantic]
    for p in lexical:
        by_id.setdefault(p["arxiv_id"], p)["matched_by"] = ["lexical"]
    for p in semantic:
        existing = by_id.get(p["arxiv_id"])
        if existing is None:
            p["matched_by"] = ["semantic"]
            by_id[p["arxiv_id"]] = p
        else:
            existing["matched_by"] = existing.get("matched_by", []) + ["semantic"]

    scores = _rrf_scores([lex_ids, sem_ids], config.RRF_K)
    ordered_ids = sorted(scores, key=lambda i: scores[i], reverse=True)
    fused = [by_id[i] for i in ordered_ids if i in by_id]
    return fused[:limit], "hybrid"


def arxiv_search(query: str, limit: int = 25) -> list[dict]:
    """Live relevance search across all of arXiv (not just the local library).

    Returns store-ready paper dicts, each tagged ``in_library`` so the dashboard
    can show "Add" vs "In library". Does not save anything — adding is an explicit
    step (see pipeline.add_papers_by_ids)."""
    papers = arxiv_client.search_arxiv(query, max_results=limit)
    have = store.existing_ids([p["arxiv_id"] for p in papers])
    for p in papers:
        p["in_library"] = p["arxiv_id"] in have
    return papers
