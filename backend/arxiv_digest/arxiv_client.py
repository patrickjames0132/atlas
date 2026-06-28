"""Fetch papers directly from the arXiv API (via the `arxiv` package).

This replaces the old Gmail-fetch + email-parse approach: no OAuth, no email
format quirks — just a structured query against arXiv, filtered to the subject
categories you follow and to a single submission date.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import arxiv

from . import config


def _short_id(result: arxiv.Result) -> str:
    """Stable arXiv id with the version suffix stripped (e.g. '2406.12345')."""
    return result.get_short_id().split("v")[0]


def fetch_papers_for_date(
    target_date: str,
    categories: Optional[list[str]] = None,
    max_results: Optional[int] = None,
) -> list[dict]:
    """Return papers SUBMITTED on `target_date` (YYYY-MM-DD) as store-ready dicts.

    Filters arXiv by ``submittedDate`` (a GMT day-range) intersected with the
    categories you follow. Results come back date-descending; we keep the whole
    day's batch up to ``max_results``.
    """
    categories = categories or config.ARXIV_CATEGORIES
    max_results = max_results or config.ARXIV_MAX_RESULTS

    # arXiv wants submittedDate as YYYYMMDDTTTT in GMT; cover the full day.
    day = datetime.strptime(target_date, "%Y-%m-%d")
    start = day.strftime("%Y%m%d0000")
    end = day.strftime("%Y%m%d2359")

    # e.g. "(cat:cs.LG OR cat:cs.AI) AND submittedDate:[202406260000 TO 202406262359]"
    cat_query = " OR ".join(f"cat:{c}" for c in categories)
    query = f"({cat_query}) AND submittedDate:[{start} TO {end}]"
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    papers: list[dict] = []
    for result in arxiv.Client().results(search):
        arxiv_id = _short_id(result)
        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": " ".join(result.title.split()),
                "authors": ", ".join(a.name for a in result.authors),
                "categories": " ".join(result.categories),
                "abstract": " ".join(result.summary.split()),
                "url": f"https://arxiv.org/abs/{arxiv_id}",
            }
        )
    return papers
