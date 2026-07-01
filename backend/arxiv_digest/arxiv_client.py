"""Fetch papers directly from the arXiv API (via the `arxiv` package).

This replaces the old Gmail-fetch + email-parse approach: no OAuth, no email
format quirks — just a structured query against arXiv, filtered to the subject
categories you follow and to a submission-date range.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import arxiv

from . import config

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

    papers: list[dict] = []
    for result in _client.results(search):
        arxiv_id = _short_id(result)
        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": " ".join(result.title.split()),
                "authors": ", ".join(a.name for a in result.authors),
                "categories": " ".join(result.categories),
                "abstract": " ".join(result.summary.split()),
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                # The paper's own submission day (GMT), so multi-day ranges land
                # in the right per-date bucket.
                "digest_date": result.published.date().isoformat(),
            }
        )
    return papers
