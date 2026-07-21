"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Ungrounded free-text search across OpenAlex — the OpenAlex twin of
``semantic_scholar/search.py``.

When the user picks **OpenAlex** as the graph provider, seed discovery searches
here instead of S2. OpenAlex's ``search=`` parameter runs a relevance search over
title + abstract + fulltext, returning works ranked by ``relevance_score`` (the
default sort when ``search=`` is present), which is exactly what a "find me a
paper to drop on the canvas" search wants.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from . import client, nodes


def _filter_clause(
    year_from: int | None, year_to: int | None, fields: list[str] | None
) -> str | None:
    """Build OpenAlex's combined ``filter=`` value for a search.

    OpenAlex combines filter keys with ``,`` and OR-values within a key with
    ``|``. A year window becomes ``from/to_publication_date`` clauses (OpenAlex
    filters on full dates, so a year bound is a Jan-1 / Dec-31 boundary); a field
    selection becomes a ``topics.field.id:fields/<id>|…`` OR clause.

    Args:
        year_from: Earliest publication year (inclusive), or None for no floor.
        year_to: Latest publication year (inclusive), or None for no ceiling.
        fields: OpenAlex field ids (the numeric part of ``fields/<id>``) to
            restrict to (any-of), or None/empty for no field filter.

    Returns:
        The ``filter=`` value (e.g. ``"topics.field.id:fields/17,
        from_publication_date:2016-01-01"``), or None when nothing is set.
    """
    clauses = []
    if fields:
        clauses.append("topics.field.id:" + "|".join(f"fields/{field_id}" for field_id in fields))
    if year_from:
        clauses.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        clauses.append(f"to_publication_date:{year_to}-12-31")
    return ",".join(clauses) or None


def search_papers(
    query: str,
    limit: int,
    year_from: int | None = None,
    year_to: int | None = None,
    fields: list[str] | None = None,
) -> list[dict]:
    """Relevance-search OpenAlex's whole corpus for papers matching a query.

    The OpenAlex counterpart of ``s2.search_papers``.

    Args:
        query: Free-text search terms.
        limit: Maximum hits to return (OpenAlex caps ``per-page`` at 200).
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.
        fields: OpenAlex **field ids** to restrict to (any-of), or None. These
            are OpenAlex's own top-level fields (``openalex.vocab``), *not* S2's
            field-of-study names — the two vocabularies are disjoint.

    Returns:
        Relevance-ranked normalized node dicts (the same shape S2 search hits and
        graph neighbors use), skipping works with no usable id.

    Raises:
        client.OpenAlexError: When the request fails after retries.
    """
    params = {
        "search": query,
        "per-page": str(min(limit, 200)),
        "select": nodes.NEIGHBOR_SELECT,
    }
    filter_clause = _filter_clause(year_from, year_to, fields)
    if filter_clause:
        params["filter"] = filter_clause
    data = client.request(client.works_url(params))
    results = (data.get("results") or []) if isinstance(data, dict) else []
    hits = [nodes.node(work) for work in results]
    return [hit for hit in hits if hit]
