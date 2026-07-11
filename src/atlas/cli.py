"""CLI entry point for Atlas (the ``atlas`` console script).

Usage:
    uv run atlas serve                  # start the API + Atlas frontend
    uv run atlas serve --port 5050      # ...on a different port (or --host)
    uv run atlas --help                 # see all commands

Every command imports lazily so ``--help`` (and each command) never pays
the import cost of the parts it doesn't touch.
"""

from __future__ import annotations

import click


@click.group(help="arXiv Atlas — interactive citation/similarity graph explorer.")
def cli() -> None:
    """The click command group; subcommands attach below."""


@cli.command(help="Run the Flask API + Atlas frontend.")
@click.option("--host", default=None, help="Interface to bind (default: config.server.host).")
@click.option(
    "--port", type=int, default=None, help="Port to bind (default: config.server.port)."
)
def serve(host: str | None, port: int | None) -> None:
    """Start the Flask dev server (API + built frontend).

    Args:
        host: Interface to bind; overrides ``config.server.host`` when given —
            e.g. ``0.0.0.0`` to expose the server on the network.
        port: Port to bind; overrides ``config.server.port`` when given — handy
            for a second instance or when 5000 is busy.

    Returns:
        None (blocks until the server exits).
    """
    from atlas import app as app_module

    app_module.main(host=host, port=port)


# --- Bring-your-own sources (the local semantic library) ---------------------


@cli.command(help="Ingest a PDF file or URL into the source library.")
@click.argument("target")
@click.option("--title", default=None, help="Override the source title.")
def ingest(target: str, title: str | None) -> None:
    """Ingest a PDF file or a URL into the local source library.

    Args:
        target: A filesystem path to a PDF, or an http(s) URL.
        title: Optional display title (defaults to the filename / page title).

    Raises:
        click.ClickException: When ingestion fails — the ``SourceError``
            text is the message (unavailable embeddings, scanned PDF,
            unreachable URL), shown cleanly instead of a traceback.
    """
    from atlas.services import sources

    try:
        if target.startswith(("http://", "https://")):
            src = sources.ingest_url(target, title=title)
        else:
            src = sources.ingest_pdf(target, title=title)
    except sources.SourceError as exc:
        raise click.ClickException(str(exc)) from exc
    pages = f", {src['pages']} pages" if src.get("pages") else ""
    click.echo(f"Ingested [{src['kind']}] “{src['title']}” — {src['n_chunks']} chunks{pages}")
    click.echo(f"  id: {src['id']}")


@cli.command("sources", help="List sources in the library.")
def sources_list() -> None:
    """Print every source in the library, one row per source."""
    from atlas.services import sources

    rows = sources.list_sources()
    if not rows:
        click.echo("No sources yet. Add one with:  ingest <pdf-or-url>")
        return
    for source in rows:
        pages = f"{source['pages']}p" if source.get("pages") else "—"
        click.echo(
            f"{source['id']}  [{source['kind']:3}] {pages:>5} "
            f"{source['n_chunks']:>5}ch  {source['title']}"
        )


@cli.command("search-sources", help="Semantic search over the library.")
@click.argument("query")
@click.option("--source", default=None, help="Restrict to one source id.")
@click.option("-k", "top_k", type=int, default=None, help="Number of passages.")
def search_sources(query: str, source: str | None, top_k: int | None) -> None:
    """Semantic-search the library and print the top passages.

    Args:
        query: What to look for — a concept or question.
        source: Restrict retrieval to one source's id (optional).
        top_k: Number of passages (defaults to ``config.sources.retrieval.search_k``).
    """
    from atlas.services import sources

    hits = sources.search(query, top_k=top_k, source_ids=[source] if source else None)
    if not hits:
        click.echo("No matches (library empty, or embeddings unavailable).")
        return
    for number, hit in enumerate(hits, 1):
        location = f"p.{hit['page']}" if hit.get("page") else "web"
        snippet = " ".join(hit["text"].split())[:280]
        click.echo(f"\n[{number}] {hit['source_title']} · {location} · score={hit['score']:.3f}")
        click.echo(f"    {snippet}…")


@cli.command(help="Delete a source by id.")
@click.argument("source_id")
def forget(source_id: str) -> None:
    """Delete a source (and its chunks/vectors) by id.

    Args:
        source_id: The source's id, as shown by the ``sources`` command.
    """
    from atlas.services import sources

    click.echo("Deleted." if sources.delete_source(source_id) else "No such source.")


if __name__ == "__main__":
    cli()
