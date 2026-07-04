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
from typing import Optional

from .. import config
from ..integrations import arxiv_client
from ..storage import cache


def arxiv_search(
    query: str,
    limit: int = 25,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    categories: Optional[list[str]] = None,
) -> list[dict]:
    """Relevance-search all of arXiv to find a seed paper.

    Args:
        query: Keywords, a title, an author, or an arXiv id / URL (an id/URL
            fetches that exact paper instead of a keyword hunt; filters don't
            apply to an explicit id).
        limit: Maximum papers to return.
        year_from: Earliest submission year (inclusive), or None.
        year_to: Latest submission year (inclusive), or None.
        categories: arXiv category codes to restrict to (any-of), or None.

    Returns:
        Relevance-ranked paper dicts (see ``arxiv_client._to_paper``). Saves
        nothing.

    Raises:
        arxiv.ArXivError: When the arXiv API fails after the client's
            built-in retries.
    """
    return arxiv_client.search_arxiv(
        query, max_results=limit,
        year_from=year_from, year_to=year_to, categories=categories,
    )


def local_search(
    query: str,
    limit: int = 10,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> list[dict]:
    """Search papers already sitting in the local graph-snapshot cache.

    Matches every whitespace token of ``query`` against a paper's title +
    authors (case-insensitive substring). Stale snapshots still count — a
    paper's title doesn't expire. Results are deduped across snapshots
    (keeping whichever record carries more detail) and ranked: whole-phrase
    title matches first, then papers explored directly as seeds, then by
    citation count.

    Args:
        query: The search text; blank/whitespace-only returns no hits.
        limit: Maximum hits to return.
        year_from: Earliest publication year (inclusive), or None. When a
            bound is set, papers with no known year are excluded — a user
            filtering by date doesn't want undatable hits.
        year_to: Latest publication year (inclusive), or None.

    Returns:
        Hit dicts with keys ``id, arxiv_id, title, authors, year,
        citation_count, url, has_graph`` — ``has_graph`` is True when a
        *fresh* snapshot exists for the paper as a seed, i.e. exploring it
        won't touch the S2 API. (No category filter here — S2 nodes don't
        carry arXiv categories.)

    Raises:
        sqlite3.Error: On cache database failures.
    """
    tokens = [t for t in (query or "").lower().split() if t]
    if not tokens:
        return []
    phrase = " ".join(tokens)

    def year_ok(n: dict) -> bool:
        """Apply the optional year window to a candidate node.

        Args:
            n: The candidate node dict.

        Returns:
            True when no bound is set, or the node's year falls inside the
            window (unknown years fail a bounded filter).
        """
        if year_from is None and year_to is None:
            return True
        y = n.get("year")
        if not isinstance(y, int):
            return False
        if year_from is not None and y < year_from:
            return False
        if year_to is not None and y > year_to:
            return False
        return True

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
            if not year_ok(n):
                continue
            prev = best.get(pid)
            # Across snapshots the same paper may appear as a bare neighbor or a
            # hydrated seed — keep whichever record carries more detail.
            if prev is None or (n.get("authors") and not prev.get("authors")):
                best[pid] = n

    def rank(n: dict) -> tuple:
        """Sort key: phrase-in-title first, then seeds, then citation count.

        Args:
            n: A candidate node dict.

        Returns:
            A tuple that sorts better matches first.
        """
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
