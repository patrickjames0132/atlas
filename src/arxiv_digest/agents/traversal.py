"""Day-cached Semantic Scholar traversal for agent workflows: one hop of
references / citations / similar work, and a free-text paper search.

This is the cached, agent-tuned layer over
``integrations.semantic_scholar.traversal`` (which talks to the live API and
caches nothing) — same name, different job, and the cache is the point: the
orchestrator's history backfill and the researcher's ``expand_node`` /
``search_papers`` tools re-hit the same hops constantly within a session, and
the rate-limited S2 API must not pay for each repeat. Results are cached for
``config.graph.cache_ttl`` (the same day-long TTL as a graph snapshot —
citation data changes slowly).

Plumbing, not tools: no model ever calls these directly. The researcher's tools
wrap them with budgets, visited-sets, and numbering; the backfill loops over
``neighbors`` raw.
"""

from __future__ import annotations

from typing import Literal

from ..config import config
from ..integrations import semantic_scholar as s2
from ..storage import cache

Relation = Literal["references", "citations", "similar"]
"""The three hop directions an agent can expand along — the graph legend's
three colors."""

REL_TAG: dict[Relation, Literal["reference", "citation", "similar"]] = {
    "references": "reference",
    "citations": "citation",
    "similar": "similar",
}
"""Hop relation (plural, the tool argument) -> the edge type tag (singular)
stored on discovered nodes and edges."""


def neighbors(paper_id: str, relation: Relation, limit: int) -> list[dict]:
    """Fetch one hop of S2 neighbors for a paper, cached for a day.

    Args:
        paper_id: The S2 paperId to expand from.
        relation: Which hop to take — ``references`` (papers it cites),
            ``citations`` (papers citing it), or ``similar``
            (embedding-similar recommendations).
        limit: Maximum neighbors to fetch. Part of the cache key — a hop
            cached at one limit isn't reused for another.

    Returns:
        ``[{"node": ..., "influential"?: bool}]`` entries from the matching
        S2 endpoint.

    Raises:
        s2.S2Error: When the S2 request fails after retries (cache misses
            only — cached hops never touch the network).
    """
    cache_key = f"expand:{relation}:{paper_id}:{limit}"
    cached = cache.get(cache_key, config.graph.cache_ttl)
    if cached is not None:
        return cached
    if relation == "references":
        hits = s2.references(paper_id, limit)
    elif relation == "citations":
        hits = s2.citations(paper_id, limit)
    else:
        hits = s2.recommendations(paper_id, limit)
    cache.set(cache_key, hits)
    return hits


def search(
    query: str,
    limit: int,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[dict]:
    """Run a free-text S2 search, cached for a day.

    The cache key normalizes the query (stripped, lowercased) so trivially
    different phrasings of the same search share an entry; S2 itself still
    receives the query as given.

    Args:
        query: Free-text search terms.
        limit: Maximum hits to fetch. Part of the cache key.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.

    Returns:
        ``[{"node": ...}]`` hits, in the traversal shape.

    Raises:
        s2.S2Error: When the S2 request fails after retries (cache misses
            only).
    """
    normalized = query.strip().lower()
    cache_key = f"search:{normalized}:{year_from or ''}-{year_to or ''}:{limit}"
    cached = cache.get(cache_key, config.graph.cache_ttl)
    if cached is not None:
        return cached
    hits = s2.search_papers(query, limit, year_from, year_to)
    cache.set(cache_key, hits)
    return hits
