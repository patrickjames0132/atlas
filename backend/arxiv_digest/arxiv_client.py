"""Fetch recent papers directly from the arXiv API (via the `arxiv` package).

This replaces the old Gmail-fetch + email-parse approach: no OAuth, no email
format quirks — just a structured query against arXiv, filtered to the subject
categories you follow.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import arxiv

from . import config


def _short_id(result: arxiv.Result) -> str:
    """Stable arXiv id with the version suffix stripped (e.g. '2406.12345')."""
    return result.get_short_id().split("v")[0]


def fetch_recent_papers(
    categories: Optional[list[str]] = None,
    lookback_days: Optional[int] = None,
    max_results: Optional[int] = None,
) -> list[dict]:
    """Return recent papers in the given categories as store-ready dicts.

    "Latest announced batch": results are sorted by submission date (newest
    first) and we keep everything submitted within `lookback_days`. Because the
    feed is date-descending, we can stop as soon as we pass the cutoff.
    """
    categories = categories or config.ARXIV_CATEGORIES
    lookback_days = lookback_days if lookback_days is not None else config.ARXIV_LOOKBACK_DAYS
    max_results = max_results or config.ARXIV_MAX_RESULTS

    # e.g. "cat:cs.LG OR cat:cs.AI OR cat:cs.CL OR cat:cs.CV"
    query = " OR ".join(f"cat:{c}" for c in categories)
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    papers: list[dict] = []
    for result in arxiv.Client().results(search):
        if result.published < cutoff:
            break  # everything after this is older — stop early
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
