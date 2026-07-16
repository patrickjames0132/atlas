"""Turn the downloaded JSONL.gz shards into queryable Parquet, via DuckDB.

DuckDB does the whole transform — it reads gzipped JSONL and writes Parquet
natively, so there's no pandas/pyarrow step. Two datasets, two layouts, each
chosen for the one query the app runs (a single seed's citers):

* **papers** → ``parquet/papers/*.parquet``, one file per input shard, projected
  down to the columns the graph needs (``corpusid``, the external ids, title,
  year, date, citation count, authors-as-JSON). Plus an **arXiv index**
  (``parquet/arxiv_index/*.parquet`` — just ``arxiv_id → corpusid`` for rows that
  have an arXiv id) so resolving a seed's corpus id is a small sorted lookup, not
  a 200M-row scan.
* **citations** → ``parquet/citations/bucket=<N>/…``, **hash-partitioned on
  ``citedcorpusid``** (``citedcorpusid % NBUCKETS``). A citer lookup filters to
  one bucket, so it reads ~1/N of the 2.4B-row edge list instead of all of it —
  the local equivalent of the citation-count sort the live API never offered.

Ingest is **idempotent and incremental**: a shard whose Parquet output already
exists is skipped, so a rerun after an interrupted ingest resumes. Only when a
dataset finishes does the caller flip ``CURRENT`` to this release (see the CLI),
so the app never queries a half-built corpus.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import duckdb

from .datasets import CorpusError
from .paths import ReleasePaths

log = logging.getLogger(__name__)

#: Number of hash buckets the citation edge list is partitioned into on
#: ``citedcorpusid``. 1024 keeps each bucket ~2.3M edges (≈ tens of MB), small
#: enough that a single seed's lookup touches one bucket cheaply, without so many
#: partitions that directory listing dominates. The **query side must use the
#: same modulus**, so it's imported from here, never re-hardcoded.
NBUCKETS = 1024

#: Explicit read schemas — projecting at read time (rather than inferring) keeps
#: ingest fast and immune to a stray shard with an odd field. ``externalids`` and
#: ``authors`` stay JSON: the arXiv/DOI ids are pulled out below, and authors are
#: formatted lazily at query time (only for the handful of citers actually shown).
_PAPERS_COLUMNS = (
    "{'corpusid': 'BIGINT', 'externalids': 'JSON', 'title': 'VARCHAR', "
    "'year': 'INTEGER', 'publicationdate': 'VARCHAR', 'citationcount': 'BIGINT', "
    "'authors': 'JSON'}"
)
_CITATIONS_COLUMNS = (
    "{'citingcorpusid': 'BIGINT', 'citedcorpusid': 'BIGINT', 'isinfluential': 'BOOLEAN'}"
)

#: Progress callback: ``(dataset, shard_filename, shard_index, shard_total)``.
ProgressFn = Callable[[str, str, int, int], None]


def _connect() -> duckdb.DuckDBPyConnection:
    """A DuckDB connection tuned for a bulk single-machine ingest.

    The one setting that matters is ``partitioned_write_max_open_files``.
    DuckDB defaults it to **100**, and a ``PARTITION_BY`` spanning more partitions
    than it can hold open has to close and reopen them as it cycles through — but
    a closed Parquet file can't be appended to, so every reopen starts a **new**
    one. Against :data:`NBUCKETS` = 1024 that turned a single citations shard into
    ~21k files averaging 3.5 KB, nearly all Parquet footer rather than data, on a
    trajectory to ~8M files for the release. File *creation*, not throughput,
    became the bottleneck (measured: ~2.8 min/shard, ~18h projected; merely
    listing the output directory timed out). Holding every bucket open costs one
    file per bucket per shard instead — ~1024, at ~70 KB each.

    Threads and memory are left at DuckDB's own defaults, which it sizes to the
    machine (16 threads / 25 GiB here). They used to be pinned to 8 and 8GB, which
    contradicted this docstring's own intent and made the file explosion *worse* —
    a tighter memory limit forces the partition writers to flush sooner, and every
    premature flush is another small file.

    Returns:
        An in-memory connection sized for the whole box — the ingest is the one
        place we want that.
    """
    connection = duckdb.connect(":memory:")
    # Headroom over NBUCKETS so no bucket ever has to be evicted mid-shard.
    connection.execute(f"SET partitioned_write_max_open_files={NBUCKETS + 24}")
    return connection


def _read_json(path_glob: str, columns: str) -> str:
    """A DuckDB ``read_json`` call over gzipped newline-delimited JSON shards."""
    return (
        f"read_json('{path_glob}', format='newline_delimited', "
        f"compression='gzip', columns={columns})"
    )


def _ingest_papers_shard(
    connection: duckdb.DuckDBPyConnection, shard: Path, out_dir: Path
) -> None:
    """Project one papers shard down to the graph columns and write its Parquet.

    Args:
        connection: The DuckDB connection.
        shard: The input ``.gz`` shard.
        out_dir: ``parquet/papers`` — the output file is named after the shard.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / (shard.stem + ".parquet")
    connection.execute(
        f"""
        COPY (
            SELECT
                corpusid,
                json_extract_string(externalids, '$.ArXiv') AS arxiv_id,
                json_extract_string(externalids, '$.DOI')   AS doi,
                title,
                year,
                publicationdate,
                citationcount,
                authors
            FROM {_read_json(shard.as_posix(), _PAPERS_COLUMNS)}
            WHERE corpusid IS NOT NULL
        ) TO '{out_file.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
        """
    )


def _ingest_citations_shard(
    connection: duckdb.DuckDBPyConnection, shard: Path, out_dir: Path
) -> None:
    """Write one citations shard, hash-partitioned on ``citedcorpusid``.

    The shard stem seeds the partition filenames so shards never collide within a
    ``bucket=`` directory. Sorting by ``citedcorpusid`` within the write gives the
    Parquet row-group zone maps that let a single-seed query skip most of a bucket.

    Args:
        connection: The DuckDB connection.
        shard: The input ``.gz`` shard.
        out_dir: ``parquet/citations`` — the partition root.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    connection.execute(
        f"""
        COPY (
            SELECT
                citingcorpusid,
                citedcorpusid,
                isinfluential,
                citedcorpusid % {NBUCKETS} AS bucket
            FROM {_read_json(shard.as_posix(), _CITATIONS_COLUMNS)}
            WHERE citedcorpusid IS NOT NULL AND citingcorpusid IS NOT NULL
            ORDER BY citedcorpusid
        ) TO '{out_dir.as_posix()}'
        (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (bucket),
         FILENAME_PATTERN '{shard.stem}_{{i}}', OVERWRITE_OR_IGNORE)
        """
    )


def _build_arxiv_index(connection: duckdb.DuckDBPyConnection, paths: ReleasePaths) -> None:
    """Build the ``arxiv_id → corpusid`` lookup from the ingested papers Parquet.

    A seed is nearly always an arXiv id, so resolving it to a corpus id is the
    hot path; this index (only the rows that *have* an arXiv id — a few million,
    sorted) keeps that a small read rather than a scan of all 200M papers.

    Args:
        connection: The DuckDB connection.
        paths: The release's paths (reads ``parquet/papers``, writes
            ``parquet/arxiv_index``).
    """
    papers_glob = (paths.parquet_dataset("papers") / "*.parquet").as_posix()
    index_dir = paths.parquet / "arxiv_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    connection.execute(
        f"""
        COPY (
            SELECT arxiv_id, corpusid
            FROM read_parquet('{papers_glob}')
            WHERE arxiv_id IS NOT NULL
            ORDER BY arxiv_id
        ) TO '{(index_dir / "arxiv_index.parquet").as_posix()}'
        (FORMAT parquet, COMPRESSION zstd)
        """
    )


def ingest_release(
    release_id: str,
    *,
    datasets_wanted: tuple[str, ...] = ("papers", "citations"),
    on_progress: ProgressFn | None = None,
) -> None:
    """Ingest a downloaded release's shards into queryable Parquet.

    Incremental: a shard whose output already exists is skipped, so a rerun
    resumes after an interruption. When ``papers`` is (re)ingested, its arXiv
    index is rebuilt. Does **not** flip ``CURRENT`` — the CLI does that only once
    a full ingest succeeds, so the app never reads a half-built release.

    Args:
        release_id: The release to ingest (must already be downloaded).
        datasets_wanted: Which datasets to ingest — defaults to both. ``papers``
            is ingested before ``citations`` when both are present, so the arXiv
            index is ready.
        on_progress: Optional per-shard callback (see :data:`ProgressFn`).

    Raises:
        CorpusError: When the corpus root is unset or a dataset has no downloaded
            shards to ingest.
    """
    from .paths import release_paths

    paths = release_paths(release_id)
    if paths is None:
        raise CorpusError("config.storage.s2_corpus_dir is not set — nothing to ingest")
    connection = _connect()

    # papers first (citations don't depend on it, but the arXiv index does, and
    # ordering keeps a combined run's index fresh before anything queries it).
    for dataset in sorted(datasets_wanted, key=lambda name: name != "papers"):
        raw_dir = paths.raw_dataset(dataset)
        shards = sorted(raw_dir.glob("*.gz"))
        if not shards:
            raise CorpusError(f"no downloaded {dataset} shards under {raw_dir}")
        out_dir = paths.parquet_dataset(dataset)
        for index, shard in enumerate(shards, start=1):
            if on_progress:
                on_progress(dataset, shard.name, index, len(shards))
            if dataset == "papers":
                if (out_dir / (shard.stem + ".parquet")).exists():
                    continue
                _ingest_papers_shard(connection, shard, out_dir)
            else:
                # A citations shard's outputs are spread across bucket dirs; a
                # marker file records completion so a rerun can skip it cleanly.
                marker = out_dir / "_done" / (shard.stem + ".ok")
                if marker.exists():
                    continue
                _ingest_citations_shard(connection, shard, out_dir)
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.touch()
        if dataset == "papers":
            log.info("building arXiv index for %s", release_id)
            _build_arxiv_index(connection, paths)

    connection.close()
