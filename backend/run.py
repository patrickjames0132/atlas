#!/usr/bin/env python3
"""CLI entry point for arXiv Atlas.

Usage:
    uv run python backend/run.py serve      # start the API + Atlas frontend
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the package importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from arxiv_digest import app as app_module  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="arXiv Atlas")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="Run the Flask API + Atlas frontend")

    args = parser.parse_args()
    if args.command == "serve":
        app_module.main()


if __name__ == "__main__":
    main()
