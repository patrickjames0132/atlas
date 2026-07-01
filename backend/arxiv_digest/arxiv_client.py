"""Fetch papers directly from the arXiv API (via the `arxiv` package).

This replaces the old Gmail-fetch + email-parse approach: no OAuth, no email
format quirks — just a structured query against arXiv, filtered to the subject
categories you follow and to a submission-date range.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import arxiv

from . import config

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


def fetch_papers_in_range(
    start_date: str,
    end_date: str,
    categories: Optional[list[str]] = None,
) -> list[dict]:
    """Return papers SUBMITTED in [start_date, end_date] as store-ready dicts.

    Both dates are inclusive YYYY-MM-DD strings. Filters arXiv by
    ``submittedDate`` (a GMT range) intersected with the categories you follow.
    There is no result cap — the whole matching batch is returned, which for a
    wide range across many categories can be a lot of papers (and slow, since
    arXiv paginates ~100 at a time). Each paper carries its own ``digest_date``
    (its actual submission day) so a range spanning multiple days is stored
    per-day.
    """
    categories = categories or config.ARXIV_CATEGORIES

    # arXiv wants submittedDate as YYYYMMDDTTTT in GMT; cover the full range.
    start = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d0000")
    end = datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m%d2359")

    # e.g. "(cat:cs.LG OR cat:cs.AI) AND submittedDate:[202406240000 TO 202406262359]"
    cat_query = " OR ".join(f"cat:{c}" for c in categories)
    query = f"({cat_query}) AND submittedDate:[{start} TO {end}]"
    # max_results=None tells the arxiv client to page through every result.
    search = arxiv.Search(
        query=query,
        max_results=None,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    return [_to_paper(result) for result in _client.results(search)]


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


def fetch_by_ids(arxiv_ids: list[str]) -> list[dict]:
    """Fetch specific papers by arXiv id as store-ready dicts (authoritative —
    used when adding a live search result to the library)."""
    ids = [i for i in (arxiv_ids or []) if i]
    if not ids:
        return []
    search = arxiv.Search(id_list=ids)
    return [_to_paper(result) for result in _client.results(search)]
