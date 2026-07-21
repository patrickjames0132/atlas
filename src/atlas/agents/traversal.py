"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Day-cached, provider-aware traversal for agent workflows: one hop of
references / citations / similar work, and a free-text paper search.

This is the cached, agent-tuned layer over the ``integrations`` traversal
clients (which talk to the live API and cache nothing) — same name, different
job, and the cache is the point: the researcher's ``expand_node`` /
``search_papers`` tools re-hit the same hops constantly within a session, and
the rate-limited APIs must not pay for each repeat. Results are cached for
``config.graph.cache_ttl`` (the same day-long TTL as a graph snapshot).

Both hops and search follow the **selected graph provider** (v5.2.0), so an
OpenAlex graph expands/searches OpenAlex — not S2 — keeping the pulled-in nodes
in the same id space as the graph. Under S2, ``similar`` is SPECTER2
recommendations; under OpenAlex it's ``related_works`` (concept/citation
overlap — weaker, but the closest analogue).

Plumbing, not tools: no model ever calls these directly. The researcher's tools
wrap them with budgets, visited-sets, and numbering.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from typing import Literal

from ..config import config
from ..integrations import openalex
from ..integrations import semantic_scholar as s2
from ..services.graph import Provider
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


def _openalex_neighbors(node_id: str, relation: Relation, limit: int) -> list[dict]:
    """One hop of OpenAlex neighbors for a graph node.

    The node id is an OpenAlex-shaped id (``DOI:``/``ARXIV:``/``W…``), so we
    first resolve it to the OpenAlex work, then hop: ``references`` via
    ``cited_by:``, ``citations`` via ``cites:``, ``similar`` via ``related_works``.

    Args:
        node_id: The graph node's id (an OpenAlex-provider id).
        relation: Which hop to take.
        limit: Maximum neighbors to fetch.

    Returns:
        ``[{"node": ...}]`` entries (``references``/``citations`` also carry
        ``influential: False``), or empty when the node can't be resolved.

    Raises:
        openalex.OpenAlexError: When a request fails after retries.
    """
    work = openalex.resolve_seed_work(node_id)
    work_id = openalex.bare_work_id(work) if work else None
    if not work_id:
        return []
    if relation == "references":
        return openalex.references(work_id, limit)
    if relation == "citations":
        return openalex.citations(work_id, limit)
    return openalex.related_works(work_id, limit)


def neighbors(paper_id: str, relation: Relation, limit: int, provider: Provider = "s2") -> list[dict]:
    """Fetch one hop of neighbors for a paper from the selected provider, cached.

    Args:
        paper_id: The graph node's id to expand from (an S2 paperId under the
            ``s2`` provider; a ``DOI:``/``ARXIV:``/``W…`` id under ``openalex``).
        relation: Which hop to take — ``references`` (papers it cites),
            ``citations`` (papers citing it), or ``similar`` (S2 SPECTER2
            recommendations, or OpenAlex ``related_works``).
        limit: Maximum neighbors to fetch. Part of the cache key — a hop
            cached at one limit isn't reused for another.
        provider: Which backend to hop through (matches the graph provider).

    Returns:
        ``[{"node": ..., "influential"?: bool}]`` entries.

    Raises:
        s2.S2Error: When an S2 request fails after retries (the ``s2`` provider).
        openalex.OpenAlexError: When an OpenAlex request fails (``openalex``).
    """
    # v4 key adds the provider: an S2 hop and an OpenAlex hop for the same node
    # are different data and must not share an entry.
    cache_key = f"expand:v4:{provider}:{relation}:{paper_id}:{limit}"
    cached = cache.get(cache_key, config.graph.cache_ttl)
    if cached is not None:
        return cached
    if provider == "openalex":
        hits = _openalex_neighbors(paper_id, relation, limit)
    elif relation == "references":
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
    provider: Provider = "s2",
) -> list[dict]:
    """Run a free-text search on the selected provider, cached for a day.

    The cache key normalizes the query (stripped, lowercased) so trivially
    different phrasings of the same search share an entry; the provider itself
    still receives the query as given.

    Args:
        query: Free-text search terms.
        limit: Maximum hits to fetch. Part of the cache key.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.
        provider: Which backend to search (matches the graph provider).

    Returns:
        ``[{"node": ...}]`` hits, in the traversal shape.

    Raises:
        s2.S2Error: When an S2 request fails after retries (the ``s2`` provider).
        openalex.OpenAlexError: When an OpenAlex request fails (``openalex``).
    """
    normalized = query.strip().lower()
    cache_key = f"search:{provider}:{normalized}:{year_from or ''}-{year_to or ''}:{limit}"
    cached = cache.get(cache_key, config.graph.cache_ttl)
    if cached is not None:
        return cached
    if provider == "openalex":
        # openalex.search_papers returns BARE node dicts (the seed-search shape);
        # wrap them into the traversal ``[{"node": ...}]`` shape this function
        # promises (and the researcher's search tool expects). S2's already is.
        hits = [{"node": node} for node in openalex.search_papers(query, limit, year_from, year_to)]
    else:
        hits = s2.search_papers(query, limit, year_from, year_to)
    cache.set(cache_key, hits)
    return hits
