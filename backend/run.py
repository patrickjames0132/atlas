#!/usr/bin/env python3
"""CLI entry point for arXiv Digest.

Usage:
    uv run python backend/run.py serve              # start the API + dashboard
    uv run python backend/run.py refresh            # fetch from arXiv + summarize
    uv run python backend/run.py refresh --no-summary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the package importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from arxiv_digest import app as app_module  # noqa: E402
from arxiv_digest import embeddings, pipeline, store  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="arXiv Digest")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Run the Flask API + dashboard")

    p_refresh = sub.add_parser("refresh", help="Fetch from arXiv, store, and summarize")
    p_refresh.add_argument(
        "--start", help="Pull papers submitted on/after this date (YYYY-MM-DD); default today"
    )
    p_refresh.add_argument(
        "--end", help="Pull papers submitted on/before this date (YYYY-MM-DD); default = start"
    )
    p_refresh.add_argument(
        "--no-summary", action="store_true", help="Skip AI summaries"
    )
    p_refresh.add_argument(
        "--no-embed", action="store_true", help="Skip embedding new papers"
    )

    p_embed = sub.add_parser(
        "embed", help="Backfill embeddings for stored papers (semantic search)"
    )
    p_embed.add_argument(
        "--rebuild",
        action="store_true",
        help="Clear and re-embed every paper (e.g. after changing the model)",
    )
    p_embed.add_argument(
        "--batch", type=int, default=256, help="Embedding batch size (default 256)"
    )

    args = parser.parse_args()

    if args.command == "serve":
        app_module.main()
    elif args.command == "refresh":
        store.init_db()
        result = pipeline.run(
            start_date=args.start,
            end_date=args.end,
            summarize=not args.no_summary,
            embed=not args.no_embed,
        )
        print("\nDone:", result)
    elif args.command == "embed":
        store.init_db()
        if not store.has_vectors():
            print(
                "Semantic search is unavailable (sqlite-vec didn't load). "
                "Nothing to embed."
            )
            return
        if not embeddings.available():
            print(
                "Embedding model is unavailable (ARXIV_SEMANTIC=0 or model failed "
                "to load). Nothing to embed."
            )
            return
        if args.rebuild:
            print("Clearing existing embeddings ...")
            store.clear_embeddings()
        pending = store.papers_missing_embedding()
        total = len(pending)
        print(f"Embedding {total} paper(s) ...")
        done = 0
        for i in range(0, total, args.batch):
            batch = pending[i : i + args.batch]
            done += pipeline.embed_papers(batch)
            print(f"  {min(i + args.batch, total)}/{total}")
        print(f"\nDone: embedded {done} paper(s).")


if __name__ == "__main__":
    main()
