"""Seed search against the arXiv API (via the `arxiv` package).

A relevance-ranked hunt across all of arXiv to find the paper you want to drop
into the graph (by keywords, title, author, or a pasted id / URL). Its id is then
handed to the Semantic Scholar graph builder.
"""

from __future__ import annotations

import re

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
    """Stable arXiv id with the version suffix stripped (e.g. '2406.12345')."""
    return result.get_short_id().split("v")[0]


def _to_paper(result: arxiv.Result) -> dict:
    """Map an arxiv.Result to our store-ready paper dict."""
    arxiv_id = _short_id(result)
    return {
        "arxiv_id": arxiv_id,
        "title": " ".join(result.title.split()),
        "authors": ", ".join(a.name for a in result.authors),
        "categories": " ".join(result.categories),
        "abstract": " ".join(result.summary.split()),
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        # The paper's own submission day (GMT), so it lands in the right per-date
        # bucket even when fetched by a keyword search rather than a date range.
        "digest_date": result.published.date().isoformat(),
    }


def search_arxiv(query: str, max_results: int = 25) -> list[dict]:
    """Search ALL of arXiv by keyword/title/author and return store-ready dicts.

    Unlike ``fetch_papers_in_range`` this ignores the followed categories and the
    date range — it's a relevance-ranked hunt across all of arXiv for a specific
    paper (e.g. "attention is all you need"). If ``query`` is (or contains) an
    arXiv id or abs/pdf URL, that exact paper is fetched instead of a keyword
    search. Results are capped at ``max_results`` to stay fast.
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
        boosted = f'ti:"{phrase}" OR abs:({phrase})'
        search = arxiv.Search(
            query=boosted,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
    return [_to_paper(result) for result in _client.results(search)]
