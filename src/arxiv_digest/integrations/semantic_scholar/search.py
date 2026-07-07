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
    query: str,
    limit: int,
    year_from: int | None = None,
    year_to: int | None = None,
    fields_of_study: list[str] | None = None,
) -> list[dict]:
    """Relevance-search S2's whole corpus for papers matching a free-text query.

    Args:
        query: Free-text search terms.
        limit: Maximum hits to return.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.
        fields_of_study: S2 fields of study to restrict to (a paper matches when
            it carries any of them), or None/empty for no restriction. Values
            must be S2's own field names (see ``vocab``).

    Returns:
        A list of ``{"node": <node dict>}`` entries, in the same shape as the
        traversal helpers.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    params = {"query": query, "fields": nodes.SEARCH_FIELDS, "limit": limit}
    year = _year_range(year_from, year_to)
    if year:
        params["year"] = year
    if fields_of_study:
        params["fieldsOfStudy"] = ",".join(fields_of_study)
    url = f"{config.s2.graph_url}/paper/search?{urllib.parse.urlencode(params)}"
    data = client.request(url)
    papers = (data.get("data") or []) if isinstance(data, dict) else []
    return nodes.from_papers(papers)


def match_title(title: str) -> dict | None:
    """Resolve a near-exact paper title to its S2 paper.

    S2's ``/paper/search/match`` endpoint returns its single best title
    match — used to verify an LLM-suggested title against the real corpus
    (see ``services/search``'s title resolution). The endpoint answers 404
    when nothing matches closely; that's data, not an error.

    Args:
        title: The (near-)exact paper title to resolve.

    Returns:
        The matched paper's node dict, or None when S2 has no close match.

    Raises:
        client.S2Error: When the request fails after retries (any failure
            other than the no-match 404).
    """
    params = {"query": title, "fields": nodes.SEARCH_FIELDS}
    url = f"{config.s2.graph_url}/paper/search/match?{urllib.parse.urlencode(params)}"
    try:
        data = client.request(url)
    except client.S2Error as exc:
        if exc.status == 404:
            return None
        raise
    papers = (data.get("data") or []) if isinstance(data, dict) else []
    matched = nodes.from_papers(papers)
    return matched[0]["node"] if matched else None
