"""The end-to-end pipeline: fetch (arXiv API) -> store -> summarize.

Run it from the CLI (`python backend/run.py refresh`) or trigger it from the
dashboard's Refresh button (POST /api/refresh).
"""

from __future__ import annotations

from datetime import date, timedelta

from . import arxiv_client, embeddings, store, summarizer


def _days_in_range(start_date: str, end_date: str) -> list[str]:
    """Every ISO day from start to end inclusive (start..end assumed valid)."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days = []
    cur = start
    while cur <= end:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def embed_papers(papers: list[dict]) -> int:
    """Embed any of ``papers`` that don't yet have a stored vector, and index
    them for semantic search. Returns the number embedded. No-op (returns 0) when
    the vector index or the embedding model is unavailable."""
    if not papers or not store.has_vectors() or not embeddings.available():
        return 0
    ids = [p["arxiv_id"] for p in papers]
    already = store.embedded_ids(ids)
    todo = [p for p in papers if p["arxiv_id"] not in already]
    if not todo:
        return 0
    vectors = embeddings.embed_texts([embeddings.document_text(p) for p in todo])
    if vectors is None:
        return 0
    store.upsert_embeddings([(p["arxiv_id"], v) for p, v in zip(todo, vectors)])
    return len(todo)


def add_papers_by_ids(arxiv_ids: list[str]) -> dict:
    """Fetch specific papers from arXiv by id, store and embed them. Used to add a
    live arXiv-search result to the library on demand. Deliberately does NOT touch
    the pull-coverage ledger — this is an ad-hoc keyword add, not a full
    category+date pull of a day, so it must not mark that day as covered.
    """
    store.init_db()
    papers = arxiv_client.fetch_by_ids(arxiv_ids)
    added = store.upsert_papers(papers)
    embedded = embed_papers(papers)
    return {"papers": papers, "added": added, "embedded": embedded}


def run(
    start_date: str | None = None,
    end_date: str | None = None,
    summarize: bool = False,
    embed: bool = True,
) -> dict:
    """Pull papers submitted in [start_date, end_date] (default: today) and store.

    Summaries are generated on demand per row in the dashboard, so this skips
    them by default; pass ``summarize=True`` (e.g. from a cron job) to also
    summarize everything in one go. New papers are embedded for semantic search
    unless ``embed=False``.
    """
    start_date = start_date or date.today().isoformat()
    end_date = end_date or start_date
    store.init_db()

    span = start_date if start_date == end_date else f"{start_date}..{end_date}"
    categories = store.get_followed_categories()
    print(
        f"[1/4] Fetching arXiv papers submitted on {span} "
        f"(categories: {', '.join(categories)}) ..."
    )
    papers = arxiv_client.fetch_papers_in_range(
        start_date, end_date, categories=categories
    )
    print(f"      Fetched {len(papers)} paper(s).")

    print("[2/4] Storing new papers ...")
    new_count = store.upsert_papers(papers)
    print(f"      {new_count} new paper(s) added to the database.")
    # Record which categories are now covered for each day in the range, so a
    # later pull can skip these days only while the followed set is unchanged.
    store.record_pull(_days_in_range(start_date, end_date), categories)

    embedded = 0
    if embed:
        print("[3/4] Embedding new papers for semantic search ...")
        embedded = embed_papers(papers)
        print(f"      Embedded {embedded} paper(s).")
    else:
        print("[3/4] Skipping embeddings (embed=False).")

    summarized = 0
    if summarize:
        print("[4/4] Generating AI summaries for papers that need one ...")
        pending = store.papers_needing_summary()
        summarized = summarizer.summarize_pending(pending)
        print(f"      Summarized {summarized} paper(s).")
    else:
        print("[4/4] Skipping summaries (summarize=False).")

    return {
        "papers_fetched": len(papers),
        "papers_new": new_count,
        "papers_embedded": embedded,
        "papers_summarized": summarized,
        "start_date": start_date,
        "end_date": end_date,
    }
