"""Cached Semantic Scholar traversal helpers shared by the history backfill and
the agentic tools: one hop of references / citations / similar work, and a
free-text paper search.

Both are cached for a day (the same TTL as a graph snapshot) so repeated
expansion or querying within a session doesn't hammer the rate-limited API.
"""

from __future__ import annotations

from typing import Optional

from .. import config
from ..integrations import semantic_scholar as s2
from ..storage import cache

# expand_node relation -> the edge tag stored on discovered nodes/edges.
_REL_TAG = {"references": "reference", "citations": "citation", "similar": "similar"}


def _s2_neighbors(paper_id: str, relation: str) -> list[dict]:
    """Fetch one hop of S2 neighbors for a paper, cached a day.

    Args:
        paper_id: The S2 paperId to expand from.
        relation: ``"references"``, ``"citations"``, or anything else for
            recommendations (``"similar"``).

    Returns:
        ``[{"node": ..., "influential"?: bool}]`` entries from the matching
        S2 endpoint, capped at ``AGENT_EXPAND_LIMIT``.

    Raises:
        s2.S2Error: When the S2 request fails after retries (cache misses
            only — cached hops never touch the network).
    """
    cache_key = f"expand:{relation}:{paper_id}"
    cached = cache.get(cache_key, config.GRAPH_CACHE_TTL)
    if cached is not None:
        return cached
    if relation == "references":
        hits = s2.references(paper_id, config.AGENT_EXPAND_LIMIT)
    elif relation == "citations":
        hits = s2.citations(paper_id, config.AGENT_EXPAND_LIMIT)
    else:
        hits = s2.recommendations(paper_id, config.AGENT_EXPAND_LIMIT)
    cache.set(cache_key, hits)
    return hits


def _s2_search(query: str, year_from: Optional[int], year_to: Optional[int]) -> list[dict]:
    """Run a cached free-text S2 search (same day-TTL as a graph snapshot).

    Args:
        query: Free-text search terms (normalized into the cache key).
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.

    Returns:
        ``[{"node": ...}]`` hits, capped at ``AGENT_SEARCH_LIMIT``.

    Raises:
        s2.S2Error: When the S2 request fails after retries (cache misses
            only).
    """
    cache_key = f"search:{query.strip().lower()}:{year_from or ''}-{year_to or ''}"
    cached = cache.get(cache_key, config.GRAPH_CACHE_TTL)
    if cached is not None:
        return cached
    hits = s2.search_papers(query, config.AGENT_SEARCH_LIMIT, year_from, year_to)
    cache.set(cache_key, hits)
    return hits


def _search_scope(year_from: Optional[int], year_to: Optional[int]) -> str:
    """Render a year window as a human-readable suffix for trace text.

    Args:
        year_from: Earliest year, or None.
        year_to: Latest year, or None.

    Returns:
        ``" (2016–2020)"``, ``" (since 2016)"``, ``" (through 2020)"``, or
        ``""`` when unbounded.
    """
    if year_from and year_to:
        return f" ({year_from}–{year_to})"
    if year_from:
        return f" (since {year_from})"
    if year_to:
        return f" (through {year_to})"
    return ""
