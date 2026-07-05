"""Ungrounded free-text search across all of Semantic Scholar.

Unlike references/citations/recommendations this has no source paper — so it
reaches recent or topical work that citation & similarity hops (lineage- and
embedding-biased) can't.
"""

from __future__ import annotations

import urllib.parse

from ...config import config
from . import client, nodes


def _year_range(year_from: int | None, year_to: int | None) -> str | None:
    """Format a year window for S2's ``year`` search filter.

    Args:
        year_from: Earliest year (inclusive), or None for no floor.
        year_to: Latest year (inclusive), or None for no ceiling.

    Returns:
        One of ``"2016-2020"``, ``"2020-"``, ``"-2015"`` — or None when both
        bounds are absent.
    """
    if year_from and year_to:
        return f"{year_from}-{year_to}"
    if year_from:
        return f"{year_from}-"
    if year_to:
        return f"-{year_to}"
    return None


def search_papers(
    query: str, limit: int, year_from: int | None = None, year_to: int | None = None
) -> list[dict]:
    """Relevance-search S2's whole corpus for papers matching a free-text query.

    Args:
        query: Free-text search terms.
        limit: Maximum hits to return.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.

    Returns:
        A list of ``{"node": <node dict>}`` entries, in the same shape as the
        traversal helpers.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    params = {"query": query, "fields": nodes.NEIGHBOR_FIELDS, "limit": limit}
    year = _year_range(year_from, year_to)
    if year:
        params["year"] = year
    url = f"{config.s2.graph_url}/paper/search?{urllib.parse.urlencode(params)}"
    data = client.request(url)
    papers = (data.get("data") or []) if isinstance(data, dict) else []
    return nodes.from_papers(papers)
