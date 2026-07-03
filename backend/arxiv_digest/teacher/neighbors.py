"""Cached Semantic Scholar traversal helpers shared by the history backfill and
the agentic tools: one hop of references / citations / similar work, and a
free-text paper search.

Both are cached for a day (the same TTL as a graph snapshot) so repeated
expansion or querying within a session doesn't hammer the rate-limited API.
"""

from __future__ import annotations

from typing import Optional

from .. import cache, config
from .. import semantic_scholar as s2

# expand_node relation -> the edge tag stored on discovered nodes/edges.
_REL_TAG = {"references": "reference", "citations": "citation", "similar": "similar"}


def _s2_neighbors(paper_id: str, relation: str) -> list[dict]:
    """S2 references/citations/recommendations for one hop, cached a day (same
    TTL as a graph snapshot) so repeated expansion doesn't hammer the rate limit."""
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
    """Cached free-text S2 search (same day-TTL as a graph snapshot) so repeated
    queries in a session don't re-hit the rate-limited endpoint."""
    cache_key = f"search:{query.strip().lower()}:{year_from or ''}-{year_to or ''}"
    cached = cache.get(cache_key, config.GRAPH_CACHE_TTL)
    if cached is not None:
        return cached
    hits = s2.search_papers(query, config.AGENT_SEARCH_LIMIT, year_from, year_to)
    cache.set(cache_key, hits)
    return hits


def _search_scope(year_from: Optional[int], year_to: Optional[int]) -> str:
    if year_from and year_to:
        return f" ({year_from}–{year_to})"
    if year_from:
        return f" (since {year_from})"
    if year_to:
        return f" (through {year_to})"
    return ""
