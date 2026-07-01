"""The end-to-end pipeline: fetch (arXiv API) -> store -> summarize.

Run it from the CLI (`python backend/run.py refresh`) or trigger it from the
dashboard's Refresh button (POST /api/refresh).
"""

from __future__ import annotations

from datetime import date

from . import arxiv_client, store, summarizer


def run(
    start_date: str | None = None,
    end_date: str | None = None,
    summarize: bool = False,
) -> dict:
    """Pull papers submitted in [start_date, end_date] (default: today) and store.

    Summaries are generated on demand per row in the dashboard, so this skips
    them by default; pass ``summarize=True`` (e.g. from a cron job) to also
    summarize everything in one go.
    """
    start_date = start_date or date.today().isoformat()
    end_date = end_date or start_date
    store.init_db()

    span = start_date if start_date == end_date else f"{start_date}..{end_date}"
    categories = store.get_followed_categories()
    print(
        f"[1/3] Fetching arXiv papers submitted on {span} "
        f"(categories: {', '.join(categories)}) ..."
    )
    papers = arxiv_client.fetch_papers_in_range(
        start_date, end_date, categories=categories
    )
    print(f"      Fetched {len(papers)} paper(s).")

    print("[2/3] Storing new papers ...")
    new_count = store.upsert_papers(papers)
    print(f"      {new_count} new paper(s) added to the database.")

    summarized = 0
    if summarize:
        print("[3/3] Generating AI summaries for papers that need one ...")
        pending = store.papers_needing_summary()
        summarized = summarizer.summarize_pending(pending)
        print(f"      Summarized {summarized} paper(s).")
    else:
        print("[3/3] Skipping summaries (summarize=False).")

    return {
        "papers_fetched": len(papers),
        "papers_new": new_count,
        "papers_summarized": summarized,
        "start_date": start_date,
        "end_date": end_date,
    }
