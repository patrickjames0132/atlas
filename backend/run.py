#!/usr/bin/env python3
"""CLI entry point for arXiv Atlas.

Usage:
    uv run python backend/run.py serve      # start the API + Atlas frontend
    uv run python backend/run.py --help     # see all commands
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

# Make the package importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))


@click.group(help="arXiv Atlas — interactive citation/similarity graph explorer.")
def cli() -> None:
    pass


@cli.command(help="Run the Flask API + Atlas frontend.")
def serve() -> None:
    from arxiv_digest import app as app_module
    app_module.main()


# --- Phase 3d — bring-your-own sources (local semantic library) --------------


@cli.command(help="Ingest a PDF file or URL into the source library.")
@click.argument("target")
@click.option("--title", default=None, help="Override the source title.")
def ingest(target: str, title: str | None) -> None:
    from arxiv_digest import sources
    if not sources.available():
        raise click.ClickException("Embeddings/sqlite-vec unavailable — cannot ingest.")
    if target.startswith(("http://", "https://")):
        src = sources.ingest_url(target, title=title)
    else:
        src = sources.ingest_pdf(target, title=title)
    pages = f", {src['pages']} pages" if src.get("pages") else ""
    click.echo(f"Ingested [{src['kind']}] “{src['title']}” — {src['n_chunks']} chunks{pages}")
    click.echo(f"  id: {src['id']}")


@cli.command("sources", help="List sources in the library.")
def sources_list() -> None:
    from arxiv_digest import sources
    rows = sources.list_sources()
    if not rows:
        click.echo("No sources yet. Add one with:  ingest <pdf-or-url>")
        return
    for s in rows:
        pages = f"{s['pages']}p" if s.get("pages") else "—"
        click.echo(f"{s['id']}  [{s['kind']:3}] {pages:>5} {s['n_chunks']:>5}ch  {s['title']}")


@cli.command("search-sources", help="Semantic search over the library.")
@click.argument("query")
@click.option("--source", default=None, help="Restrict to one source id.")
@click.option("-k", "k", type=int, default=None, help="Number of passages.")
def search_sources(query: str, source: str | None, k: int | None) -> None:
    from arxiv_digest import sources
    hits = sources.search(query, k=k, source_id=source)
    if not hits:
        click.echo("No matches (library empty, or embeddings unavailable).")
        return
    for i, h in enumerate(hits, 1):
        loc = f"p.{h['page']}" if h.get("page") else "web"
        snippet = " ".join(h["text"].split())[:280]
        click.echo(f"\n[{i}] {h['source_title']} · {loc} · dist={h['distance']:.3f}")
        click.echo(f"    {snippet}…")


@cli.command(help="Delete a source by id.")
@click.argument("source_id")
def forget(source_id: str) -> None:
    from arxiv_digest import sources
    click.echo("Deleted." if sources.delete_source(source_id) else "No such source.")


if __name__ == "__main__":
    cli()
