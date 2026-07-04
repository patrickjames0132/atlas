"""Seed search against the arXiv API (via the `arxiv` package).

A relevance-ranked hunt across all of arXiv to find the paper you want to drop
into the graph (by keywords, title, author, or a pasted id / URL). Its id is then
handed to the Semantic Scholar graph builder.
"""

from __future__ import annotations

import re
from typing import Optional

import arxiv

# A bare arXiv id (new-style "2406.12345" / "2406.12345v2", or old-style
# "hep-th/9901001"), optionally wrapped in an arxiv.org URL. Lets a search box
# accept a pasted id or link and fetch that exact paper instead of a keyword hunt.
_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)?"
    r"(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)",
    re.IGNORECASE,
)

# One shared client for the whole process. The client enforces arXiv's polite
# ~3s-between-requests rate limit by tracking its OWN last-request time, so a
# single reused instance paces EVERY request — both pages within a query and
# consecutive per-day pulls. Creating a fresh client per call (the old bug) gave
# each one no memory of the last request, so rapid day-by-day pulls fired with
# no gap and arXiv answered with HTTP 429. num_retries is bumped for resilience.
_client = arxiv.Client(page_size=100, delay_seconds=3.0, num_retries=5)


def _short_id(result: arxiv.Result) -> str:
    """Extract a stable arXiv id from a result.

    Args:
        result: An ``arxiv.Result`` from the client.

    Returns:
        The bare id with any version suffix stripped (e.g. ``"2406.12345"``,
        never ``"2406.12345v2"``), so the same paper always keys identically.
    """
    return result.get_short_id().split("v")[0]


def _to_paper(result: arxiv.Result) -> dict:
    """Map an ``arxiv.Result`` to the app's paper dict.

    Args:
        result: An ``arxiv.Result`` from the client.

    Returns:
        A dict with keys ``arxiv_id, title, authors, categories, abstract,
        url, published`` — whitespace collapsed, version stripped from the
        id. ``published`` is the paper's own submission day (GMT) as an ISO
        ``YYYY-MM-DD`` string.
    """
    arxiv_id = _short_id(result)
    return {
        "arxiv_id": arxiv_id,
        "title": " ".join(result.title.split()),
        "authors": ", ".join(a.name for a in result.authors),
        "categories": " ".join(result.categories),
        "abstract": " ".join(result.summary.split()),
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        # The paper's own submission day (GMT), shown in the search results
        # and filterable via year_from/year_to.
        "published": result.published.date().isoformat(),
    }


def _date_clause(year_from: Optional[int], year_to: Optional[int]) -> Optional[str]:
    """Build arXiv's ``submittedDate`` range clause for a year window.

    arXiv's query syntax wants both bounds (``[from TO to]``), so an open
    end is filled with arXiv's launch year (1991) or a far-future ceiling.

    Args:
        year_from: Earliest submission year (inclusive), or None.
        year_to: Latest submission year (inclusive), or None.

    Returns:
        ``submittedDate:[YYYY01010000 TO YYYY12312359]`` — or None when both
        bounds are absent.
    """
    if not year_from and not year_to:
        return None
    lo = f"{year_from or 1991}01010000"
    hi = f"{year_to or 2099}12312359"
    return f"submittedDate:[{lo} TO {hi}]"


def _cat_clause(categories: Optional[list[str]]) -> Optional[str]:
    """Build arXiv's category filter clause.

    Args:
        categories: Category codes (e.g. ``["cs.LG", "cs.CV"]``) — already
            validated by the caller; falsy entries are dropped.

    Returns:
        ``(cat:cs.LG OR cat:cs.CV)`` — a paper matches when it carries ANY of
        the selected categories — or None when the list is empty.
    """
    cats = [c for c in (categories or []) if c]
    if not cats:
        return None
    return "(" + " OR ".join(f"cat:{c}" for c in cats) + ")"


def search_arxiv(
    query: str,
    max_results: int = 25,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    categories: Optional[list[str]] = None,
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
        A list of paper dicts (see ``_to_paper``), relevance-ranked. Saves
        nothing.

    Raises:
        arxiv.ArXivError: When the arXiv API fails after the client's
            built-in retries (surfaced by the route as a search failure).
    """
    query = (query or "").strip()
    if not query:
        return []

    id_match = _ID_RE.fullmatch(query) or _ID_RE.fullmatch(query.rstrip("/"))
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
        cat = _cat_clause(categories)
        if cat:
            parts.append(cat)
        date = _date_clause(year_from, year_to)
        if date:
            parts.append(date)
        search = arxiv.Search(
            query=" AND ".join(parts),
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
    return [_to_paper(result) for result in _client.results(search)]
