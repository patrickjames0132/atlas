"""The end-to-end pipeline: fetch (arXiv API) -> store -> summarize.

Run it from the CLI (`python backend/run.py refresh`) or trigger it from the
dashboard's Refresh button (POST /api/refresh).
"""

from __future__ import annotations

from datetime import date

from . import arxiv_client, store, summarizer


def run(digest_date: str | None = None, summarize: bool = False) -> dict:
    """Pull papers submitted on `digest_date` (default today) and store them.

    Summaries are generated on demand per row in the dashboard, so this skips
    them by default; pass ``summarize=True`` (e.g. from a cron job) to also
    summarize everything in one go.
    """
    digest_date = digest_date or date.today().isoformat()
    store.init_db()

    categories = store.get_followed_categories()
    print(
        f"[1/3] Fetching arXiv papers submitted on {digest_date} "
        f"(categories: {', '.join(categories)}) ..."
    )
    papers = arxiv_client.fetch_papers_for_date(digest_date, categories=categories)
    print(f"      Fetched {len(papers)} paper(s).")

    print("[2/3] Storing new papers ...")
    new_count = store.upsert_papers(papers, digest_date=digest_date)
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
        "digest_date": digest_date,
    }
