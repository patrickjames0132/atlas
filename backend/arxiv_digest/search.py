"""Seed discovery: a live relevance search across arXiv, plus an instant search
over the local snapshot cache.

arXiv Atlas doesn't store a paper corpus, so "search" here is simply a thin pass
through to the arXiv API to find the paper you want to drop into the graph. Its
id is then handed to ``graph.build_graph``. (The digest era's hybrid lexical +
semantic search over a local store was retired with the v1.0 pivot.)

``local_search`` is the cache-first complement: it scans the graph snapshots
already sitting in the SQLite cache and matches papers by title/authors. It
answers instantly and works even when Semantic Scholar is rate-limiting us —
if you've seen a paper on a graph before, you can find it again offline.
"""

from __future__ import annotations

import time

from . import arxiv_client, cache, config


def arxiv_search(query: str, limit: int = 25) -> list[dict]:
    """Relevance search across all of arXiv to find a seed paper. Accepts keywords,
    a title, an author, or an arXiv id / URL. Returns paper dicts; saves nothing."""
    return arxiv_client.search_arxiv(query, max_results=limit)


def local_search(query: str, limit: int = 10) -> list[dict]:
    """Search papers already in the local graph-snapshot cache.

    Matches every whitespace token of `query` against a paper's title + authors
    (case-insensitive substring). Stale snapshots still count — a paper's title
    doesn't expire — but each hit carries ``has_graph``: True when a *fresh*
    snapshot exists for it as a seed, i.e. exploring it won't touch the S2 API.
    Results are deduped across snapshots and ranked: whole-phrase matches first,
    then seed papers, then by citation count.
    """
    tokens = [t for t in (query or "").lower().split() if t]
    if not tokens:
        return []
    phrase = " ".join(tokens)

    now = time.time()
    fresh_seeds: set[str] = set()  # ids whose own graph is cached & unexpired
    best: dict[str, dict] = {}  # paper id -> richest matching record

    for _key, snap, created in cache.scan("graph:"):
        if not isinstance(snap, dict):
            continue
        if (now - created) <= config.GRAPH_CACHE_TTL:
            seed = snap.get("seed") or {}
            fresh_seeds.update(s for s in (seed.get("arxiv_id"), seed.get("id")) if s)
        for n in snap.get("nodes") or []:
            pid = n.get("id")
            title = n.get("title") or ""
            if not pid or not title:
                continue
            haystack = f"{title} {n.get('authors') or ''}".lower()
            if not all(t in haystack for t in tokens):
                continue
            prev = best.get(pid)
            # Across snapshots the same paper may appear as a bare neighbor or a
            # hydrated seed — keep whichever record carries more detail.
            if prev is None or (n.get("authors") and not prev.get("authors")):
                best[pid] = n

    def rank(n: dict) -> tuple:
        return (
            phrase not in (n.get("title") or "").lower(),  # phrase-in-title first
            not n.get("is_seed"),  # papers you explored directly next
            -(n.get("citation_count") or 0),
        )

    hits = sorted(best.values(), key=rank)[:limit]
    return [
        {
            "id": n["id"],
            "arxiv_id": n.get("arxiv_id"),
            "title": n.get("title"),
            "authors": n.get("authors"),
            "year": n.get("year"),
            "citation_count": n.get("citation_count"),
            "url": n.get("url"),
            "has_graph": bool(
                fresh_seeds & {i for i in (n["id"], n.get("arxiv_id")) if i}
            ),
        }
        for n in hits
    ]
