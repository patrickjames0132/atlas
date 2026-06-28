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
from arxiv_digest import pipeline, store  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="arXiv Digest")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Run the Flask API + dashboard")

    p_refresh = sub.add_parser("refresh", help="Fetch from arXiv, store, and summarize")
    p_refresh.add_argument(
        "--date", help="Pull papers submitted on this date (YYYY-MM-DD); default today"
    )
    p_refresh.add_argument(
        "--no-summary", action="store_true", help="Skip AI summaries"
    )

    args = parser.parse_args()

    if args.command == "serve":
        app_module.main()
    elif args.command == "refresh":
        store.init_db()
        result = pipeline.run(digest_date=args.date, summarize=not args.no_summary)
        print("\nDone:", result)


if __name__ == "__main__":
    main()
