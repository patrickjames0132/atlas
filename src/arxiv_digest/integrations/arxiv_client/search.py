"""The public entry point: detect an id vs. a keyword query, build the
``arxiv.Search``, and normalize the results."""

from __future__ import annotations

import re

import arxiv

from ..arxiv import ID_RE  # the arXiv-id regex, now homed in the arxiv package
from . import clauses, papers

# One shared client for the whole process. The client enforces arXiv's polite
# ~3s-between-requests rate limit by tracking its OWN last-request time, so a
# single reused instance paces EVERY request — both pages within a query and
# consecutive per-day pulls. Creating a fresh client per call (the old bug) gave
# each one no memory of the last request, so rapid day-by-day pulls fired with
# no gap and arXiv answered with HTTP 429. num_retries is bumped for resilience.
_client = arxiv.Client(page_size=100, delay_seconds=3.0, num_retries=5)


def search_arxiv(
    query: str,
    max_results: int = 25,
    year_from: int | None = None,
    year_to: int | None = None,
    categories: list[str] | None = None,
) -> list[dict]:
    """Search ALL of arXiv by keyword/title/author and return paper dicts.

    A relevance-ranked hunt across all of arXiv for a specific paper (e.g.
    "attention is all you need"). If ``query`` is an arXiv id or abs/pdf URL,
    that exact paper is fetched instead of a keyword search (filters don't
    apply — an explicit id wins). For keyword queries, an explicit
    quoted-title clause is OR-ed with an abstract term-group — arXiv's plain
    free-text relevance ranks exact-title papers surprisingly low, and a bare
    unprefixed term group is malformed (arXiv answers it with an empty feed).
    Optional filters are AND-ed onto that base clause.

    Args:
        query: Keywords, a title, an author, or an arXiv id / URL. Blank
            queries short-circuit to an empty list.
        max_results: Cap on returned papers (keyword searches only; an id
            lookup returns at most the one paper).
        year_from: Earliest submission year (inclusive), or None.
        year_to: Latest submission year (inclusive), or None.
        categories: arXiv category codes to restrict to (a paper matches when
            it carries any of them), or None/empty for no restriction.

    Returns:
        A list of paper dicts (see ``papers.to_paper``), relevance-ranked.
        Saves nothing.

    Raises:
        arxiv.ArxivError: When the arXiv API fails after the client's
            built-in retries (surfaced by the route as a search failure).
    """
    query = (query or "").strip()
    if not query:
        return []

    id_match = ID_RE.fullmatch(query) or ID_RE.fullmatch(query.rstrip("/"))
    if id_match:
        search = arxiv.Search(id_list=[id_match.group(1)])
    else:
        # Boost exact title matches: arXiv's plain free-text relevance ranks the
        # actual "Attention Is All You Need" paper well below noise (often off the
        # first page entirely), but an explicit title clause floats it to the top.
        # We OR a quoted title phrase with an abstract term-group so topical
        # (non-title) searches still return broadly. Both halves MUST be
        # field-prefixed — a bare "(terms)" group is malformed and arXiv returns
        # an empty feed for it. Strip quotes/parens from the user's text so they
        # can't break the query syntax.
        phrase = re.sub(r'["()]+', " ", query).strip()
        parts = [f'(ti:"{phrase}" OR abs:({phrase}))']
        category_filter = clauses.category_clause(categories)
        if category_filter:
            parts.append(category_filter)
        date_range = clauses.date_clause(year_from, year_to)
        if date_range:
            parts.append(date_range)
        search = arxiv.Search(
            query=" AND ".join(parts),
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
    return [papers.to_paper(result) for result in _client.results(search)]
