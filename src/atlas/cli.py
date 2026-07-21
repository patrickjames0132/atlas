"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
CLI entry point for Atlas (the ``atlas`` console script).

Usage:
    uv run atlas serve                  # start the API + Atlas frontend
    uv run atlas serve --port 5050      # ...on a different port (or --host)
    uv run atlas --help                 # see all commands

Every command imports lazily so ``--help`` (and each command) never pays
the import cost of the parts it doesn't touch.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from pathlib import Path

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


# --- Offline S2 citations corpus (the real Field-Landmarks fix) --------------


@cli.group(help="Download/ingest the offline Semantic Scholar citations corpus.")
def corpus() -> None:
    """Command group for the offline S2 citations corpus.

    The bulk ``citations`` + ``papers`` Datasets releases are ~300 GB, so this is
    an operator workflow (run on your own machine, resumable), not a request-path
    action: ``download`` pulls the shards, ``ingest`` builds the queryable
    Parquet, and ``activate`` flips the app over to a finished release. See
    ``integrations/semantic_scholar/corpus/README.md``.
    """


def _require_corpus_root() -> Path:
    """The corpus root, or a clean CLI error when it isn't configured.

    Returns:
        The configured ``storage.s2_corpus`` root.

    Raises:
        click.ClickException: When it's unset — the command has nowhere to
            read or write.
    """
    from atlas.config import config

    root = config.storage.s2_corpus
    if root is None:
        raise click.ClickException(
            'config.storage.s2_corpus is not set — point it at a roomy drive '
            '(outside the repo) first, e.g. "E:\\\\s2corpus".'
        )
    return root


@corpus.command("status", help="Show the corpus root, releases, and active pointer.")
def corpus_status() -> None:
    """Print the corpus root, its releases, and which one is active."""
    from atlas.config import config
    from atlas.integrations.semantic_scholar.corpus import paths as corpus_paths

    root = config.storage.s2_corpus
    click.echo(f"corpus root: {root or '(unset — corpus off, using live S2)'}")
    if root is None:
        return
    click.echo(f"exists:      {root.exists()}")
    active = corpus_paths.read_current_release(root) if root.exists() else None
    click.echo(f"active release (CURRENT): {active or '(none)'}")

    # A release can be downloaded-not-ingested (raw subtree only) or
    # ingested-and-shards-deleted (parquet subtree only). Show them all.
    releases_dir = root / "releases"
    releases = (
        sorted(child.name for child in releases_dir.iterdir() if child.is_dir())
        if releases_dir.exists()
        else []
    )
    for release in releases:
        paths = corpus_paths.release_paths(release)
        papers_done = paths.parquet_dataset("papers").exists()
        cites_done = paths.parquet_dataset("citations").exists()
        shards = paths.raw.exists()
        click.echo(
            f"  {release}: shards={shards} papers-parquet={papers_done} "
            f"citations-parquet={cites_done}"
        )


@corpus.command("download", help="Download (or resume) a release's shards.")
@click.option("--release", "release_id", default=None, help="Release id (default: latest).")
@click.option(
    "--dataset",
    "datasets_opt",
    type=click.Choice(["papers", "citations"]),
    multiple=True,
    help="Restrict to one dataset (repeatable). Default: both.",
)
@click.option(
    "--shards",
    type=int,
    default=None,
    help="Cap shards per dataset — a quick sample (e.g. 1 ≈ 1 GB) before the full ~300 GB.",
)
def corpus_download(release_id: str | None, datasets_opt: tuple[str, ...], shards: int | None) -> None:
    """Download a release's shards, resuming any partial pull.

    Args:
        release_id: The release to download; defaults to the latest release.
        datasets_opt: Datasets to pull (``papers``/``citations``); both by default.
        shards: Optional per-dataset shard cap for a quick sample.

    Raises:
        click.ClickException: When the corpus root is unset or a download fails.
    """
    _require_corpus_root()
    from atlas.integrations.semantic_scholar.corpus import datasets, download
    from atlas.integrations.semantic_scholar.corpus.datasets import CorpusError
    from atlas.integrations.semantic_scholar.corpus.paths import DATASETS

    release_id = release_id or datasets.latest_release_id()
    wanted = datasets_opt or DATASETS
    click.echo(f"Downloading release {release_id} ({', '.join(wanted)})" + (f", {shards} shard(s) each" if shards else ""))

    def on_progress(dataset: str, filename: str, done: int, total: int | None) -> None:
        pct = f"{100 * done / total:5.1f}%" if total else "  ?  "
        click.echo(f"\r  {dataset:9} {filename[:32]:32} {done / 1e6:8.1f} MB {pct}", nl=False)

    try:
        download.download_release(
            release_id, datasets_wanted=tuple(wanted), shards=shards, on_progress=on_progress
        )
    except CorpusError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("\nDownload complete.")


@corpus.command("ingest", help="Ingest downloaded shards into queryable Parquet.")
@click.option("--release", "release_id", default=None, help="Release id (default: latest).")
@click.option(
    "--dataset",
    "datasets_opt",
    type=click.Choice(["papers", "citations"]),
    multiple=True,
    help="Restrict to one dataset (repeatable). Default: both.",
)
@click.option(
    "--activate/--no-activate",
    default=True,
    help="On success, point CURRENT at this release (the app then queries it). Default: on.",
)
def corpus_ingest(release_id: str | None, datasets_opt: tuple[str, ...], activate: bool) -> None:
    """Ingest a downloaded release to Parquet and (by default) activate it.

    Args:
        release_id: The release to ingest; defaults to the latest release.
        datasets_opt: Datasets to ingest; both by default.
        activate: Flip ``CURRENT`` to this release when the ingest succeeds.

    Raises:
        click.ClickException: When the corpus root is unset or the ingest fails.
    """
    corpus_root = _require_corpus_root()  # shards read, Parquet + CURRENT written
    from atlas.integrations.semantic_scholar.corpus import datasets, ingest
    from atlas.integrations.semantic_scholar.corpus.datasets import CorpusError
    from atlas.integrations.semantic_scholar.corpus.paths import DATASETS, write_current_release

    release_id = release_id or datasets.latest_release_id()
    wanted = datasets_opt or DATASETS
    click.echo(f"Ingesting release {release_id} ({', '.join(wanted)})…")

    def on_progress(dataset: str, filename: str, index: int, total: int) -> None:
        click.echo(f"\r  {dataset:9} shard {index}/{total}: {filename[:40]:40}", nl=False)

    try:
        ingest.ingest_release(release_id, datasets_wanted=tuple(wanted), on_progress=on_progress)
    except CorpusError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("\nIngest complete.")
    if activate and set(DATASETS).issubset(wanted):
        write_current_release(corpus_root, release_id)
        click.echo(f"Activated {release_id} (CURRENT).")
    elif activate:
        click.echo("Not activated — activate only after both datasets are ingested "
                   "(`atlas corpus activate`).")


@corpus.command("compact", help="Cluster an ingested release's papers by corpusid.")
@click.option("--release", "release_id", default=None,
              help="Release id (default: the active CURRENT release).")
def corpus_compact(release_id: str | None) -> None:
    """Compact a release's papers dataset into the clustered (sorted) layout.

    The migration path for a release ingested before v5.12.0 (whose papers are
    one file per shard, so nothing prunes and citer hydration is a full scan),
    and the recovery path after an interrupted compaction. New ingests compact
    automatically — this exists for corpora that predate that. Needs only the
    parquet root; the raw shards can be long gone. Safe to rerun: an
    already-clustered release is a fast no-op.

    Args:
        release_id: The release to compact; defaults to the active ``CURRENT``
            release (this is a maintenance pass over what's being served, so it
            defaults to what's on disk — not to the network's latest release).

    Raises:
        click.ClickException: When the corpus root is unset, no release is
            named or active, or the compaction fails.
    """
    corpus_root = _require_corpus_root()
    from atlas.integrations.semantic_scholar.corpus import ingest
    from atlas.integrations.semantic_scholar.corpus import paths as corpus_paths
    from atlas.integrations.semantic_scholar.corpus.datasets import CorpusError

    release_id = release_id or corpus_paths.read_current_release(corpus_root)
    if not release_id:
        raise click.ClickException(
            "no release named and none active — pass --release or activate one first"
        )
    click.echo(f"Compacting release {release_id} (papers → clustered by corpusid)…")
    try:
        compacted = ingest.compact_release(release_id)
    except CorpusError as exc:
        raise click.ClickException(str(exc)) from exc
    if compacted:
        click.echo("Compacted (papers clustered; arXiv index rebuilt).")
    else:
        click.echo("Already clustered — nothing to do.")


@corpus.command("activate", help="Point CURRENT at a release so the app queries it.")
@click.option("--release", "release_id", default=None, help="Release id (default: latest).")
def corpus_activate(release_id: str | None) -> None:
    """Mark a release active (write the ``CURRENT`` pointer).

    Args:
        release_id: The release to activate; defaults to the latest release.

    Raises:
        click.ClickException: When the corpus root is unset or the release's
            papers Parquet is missing (nothing to activate).
    """
    corpus_root = _require_corpus_root()
    from atlas.integrations.semantic_scholar.corpus import datasets
    from atlas.integrations.semantic_scholar.corpus.paths import (
        release_paths,
        write_current_release,
    )

    release_id = release_id or datasets.latest_release_id()
    paths = release_paths(release_id)
    if not paths.parquet_dataset("papers").exists():
        raise click.ClickException(f"release {release_id} has no ingested papers Parquet — ingest first")
    write_current_release(corpus_root, release_id)
    click.echo(f"Activated {release_id} (CURRENT).")


if __name__ == "__main__":
    cli()
