"""Turn the downloaded JSONL.gz shards into queryable Parquet, via DuckDB.

DuckDB does the whole transform — it reads gzipped JSONL and writes Parquet
natively, so there's no pandas/pyarrow step. Two datasets, two layouts, each
chosen for the one query the app runs (a single seed's citers):

* **papers** → ``parquet/papers/clustered_*.parquet``, the whole dataset
  **globally sorted by ``corpusid``**, projected down to the columns the graph
  needs (``corpusid``, the external ids, title, year, date, citation count,
  authors-as-JSON). Shards are first ingested one file each (the incremental
  unit), then a **compaction pass** rewrites them as one clustered dataset —
  global, not per-shard, because every shard spans the whole id range, so
  per-shard sorting leaves every row group covering everything and nothing
  prunes (measured: any corpusid lookup was a full 24.8 GB scan, ~33s; clustered,
  row groups own contiguous id slices and zone maps skip all but a few).
  Plus an **arXiv index** (``parquet/arxiv_index/*.parquet`` — just
  ``arxiv_id → corpusid`` for rows that have an arXiv id) so resolving a seed's
  corpus id is a small sorted lookup, not a 200M-row scan.
* **citations** → ``parquet/citations/bucket=<N>/…``, **hash-partitioned on
  ``citedcorpusid``** (``citedcorpusid % NBUCKETS``). A citer lookup filters to
  one bucket, so it reads ~1/N of the 2.4B-row edge list instead of all of it —
  the local equivalent of the citation-count sort the live API never offered.

Ingest is **idempotent and incremental**: a shard whose Parquet output (or
``_done`` marker, once compaction has folded its file away) already exists is
skipped, so a rerun after an interrupted ingest resumes. Only when a dataset
finishes does the caller flip ``CURRENT`` to this release (see the CLI), so the
app never queries a half-built corpus.

Long citations runs **recycle their worker process** every
:data:`_SHARDS_PER_WORKER` shards: the partitioned write slows down as a
process ages (~3x across the first full release — per *process*, not per
connection, tree, or shard size; see the constant's docs and docs/bugs.md),
so the shard loop runs in a single-worker pool whose child is periodically
replaced, holding every shard near cold-start speed.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from concurrent.futures import ProcessPoolExecutor
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

#: How many citations shards one worker process ingests before being replaced.
#: The partitioned write slows down **per process**, not per connection or per
#: directory: repeating the same shard-sized COPY in one process degraded
#: 3.04x over 70 iterations (~0.1s added per COPY — matching the ~0.08s/shard
#: climb measured across the real 2026-07-07 release), survived a DuckDB
#: reconnect unchanged, and reset to cold speed the moment the process was
#: replaced — while single-file COPYs of the same sorted+compressed payload
#: stayed flat, pointing at allocator/heap wear from the 1024 per-partition
#: writers rather than anything DuckDB tracks. Recycling every 16 shards
#: bounds the accumulated slowdown at ~1-2s/shard for ~0.3s of respawn cost
#: per cycle (measured; spawn re-imports this module, so keep its imports
#: lean-ish). See docs/bugs.md.
_SHARDS_PER_WORKER = 16

#: The recycled worker's cached DuckDB connection (one per worker process,
#: created on its first shard, discarded with the process). Module-level
#: because the worker function must be importable by the spawned child.
_worker_connection: duckdb.DuckDBPyConnection | None = None


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


#: Filename prefix distinguishing the compacted, globally-sorted papers files
#: from freshly ingested per-shard ones sitting in the same directory. The two
#: kinds share ``parquet/papers`` so the serving glob never has to know whether
#: a release has been compacted yet — but compaction has to tell them apart:
#: everything *without* this prefix is pending input, everything with it is a
#: previous compaction's output (also an input — a re-compaction folds it in).
_CLUSTERED_PREFIX = "clustered_"

#: The staging directory a compaction writes into before swapping its output
#: live, and the manifest that makes the swap resumable. The manifest is written
#: only after the sorted COPY completes, so its existence *is* the commit point:
#: no manifest → any staging content is garbage from an interrupted sort, start
#: over; manifest present → the sorted data is complete and only the swap
#: remains, finish it before touching the shards it replaces.
_COMPACTING_DIR = "_compacting"
_MANIFEST_NAME = "MANIFEST.json"


def _pending_papers_files(papers_dir: Path) -> list[Path]:
    """The per-shard papers files not yet folded into the clustered dataset.

    Args:
        papers_dir: The release's ``parquet/papers`` directory.

    Returns:
        The non-``clustered_*`` Parquet files at the top level, sorted — a
        release ingested before compaction existed is all-pending, which is
        exactly what lets ``compact_release`` migrate it in place.
    """
    if not papers_dir.exists():
        return []
    return sorted(
        candidate
        for candidate in papers_dir.glob("*.parquet")
        if not candidate.name.startswith(_CLUSTERED_PREFIX)
    )


def _finish_papers_swap(papers_dir: Path) -> None:
    """Complete a compaction's swap: staged clustered files replace shard files.

    Idempotent, and the crash-recovery path as much as the happy one — it runs
    off the staging manifest alone, so a swap interrupted at any point resumes
    by rerunning it. The order is what makes that safe: everything deleted here
    is already carried by the staged generation (it was the sort's input), and
    the shard markers are written only once the staged files are in place, so no
    state ever claims rows that aren't on disk.

    Args:
        papers_dir: The release's ``parquet/papers`` directory.
    """
    compacting_dir = papers_dir / _COMPACTING_DIR
    manifest_path = compacting_dir / _MANIFEST_NAME
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    generation_prefix = f"{_CLUSTERED_PREFIX}{manifest['generation']}_"
    # Everything predating this generation — shard files and older clustered
    # files alike — went into the sort, so it's all superseded.
    for stale in papers_dir.glob("*.parquet"):
        if not stale.name.startswith(generation_prefix):
            stale.unlink()
    for staged in sorted(compacting_dir.glob("*.parquet")):
        staged.replace(papers_dir / staged.name)
    marker_dir = papers_dir / "_done"
    marker_dir.mkdir(parents=True, exist_ok=True)
    for shard_stem in manifest["shards"]:
        (marker_dir / (shard_stem + ".ok")).touch()
    shutil.rmtree(compacting_dir)


def _compact_papers(connection: duckdb.DuckDBPyConnection, papers_dir: Path) -> bool:
    """Rewrite the papers dataset globally sorted by ``corpusid`` (clustered).

    The sort must be **global, not per-shard**: every shard spans the whole
    0–290M corpusid range, so sorting within one still leaves each of its row
    groups covering everything, and a scattered-id lookup hits them all.
    Sorted globally, each output row group owns a contiguous id slice and
    Parquet zone maps skip the rest — measured on a 4-file 1.8 GB subset, the
    row groups' average id-range width collapsed from the entire range to
    ~2M ids and a 63-id lookup went 1.65s → 0.65s; at full scale nothing pruned
    at all and every lookup was a 24.8 GB scan. The one-time cost is paid once
    per release: the 1.8 GB subset sorted in ~13s, but that ran in RAM — the
    full dataset exceeds the memory limit and spills, making it an external
    merge sort that measured ~10–15 minutes, not the extrapolated ~3. It keeps
    the Parquet/Athena endgame — Athena prunes on the same statistics.

    Reads *everything* at the top level — pending shard files and any previous
    generation's clustered files — sorts once, stages the output beside the
    data, then swaps it live (see :func:`_finish_papers_swap` for why the swap
    survives a crash at any point).

    Args:
        connection: The DuckDB connection.
        papers_dir: The release's ``parquet/papers`` directory.

    Returns:
        Whether anything was compacted — False when the dataset is already
        fully clustered, so callers can skip the arXiv-index rebuild too.
    """
    _finish_papers_swap(papers_dir)
    pending = _pending_papers_files(papers_dir)
    if not pending:
        return False
    log.info("compacting %d papers file(s) into a clustered dataset", len(pending))
    compacting_dir = papers_dir / _COMPACTING_DIR
    shutil.rmtree(compacting_dir, ignore_errors=True)
    compacting_dir.mkdir(parents=True)
    # The sort is bigger than the memory limit at full scale (tens of GB
    # uncompressed against DuckDB's default cap), and an in-memory database has
    # nowhere to spill unless told — so give it scratch space on the same drive
    # as the output. Cleaned up with the rest of the staging on success, or by
    # the next compaction's rmtree after a crash.
    spill_dir = papers_dir / "_spill"
    shutil.rmtree(spill_dir, ignore_errors=True)
    spill_dir.mkdir(parents=True)
    connection.execute(f"SET temp_directory='{spill_dir.as_posix()}'")
    # The sort is one long blocking statement — ~10-15 minutes at full scale,
    # not the subset-extrapolated ~3 (the spill makes it an *external* merge
    # sort, slower per GB than the in-RAM subset measurement). Let DuckDB paint
    # its own progress bar so the operator sees movement; it only appears on
    # statements outlasting its threshold, so shard COPYs and the tests stay
    # quiet.
    connection.execute("SET enable_progress_bar=true")
    generation = uuid.uuid4().hex[:8]
    connection.execute(
        f"""
        COPY (
            SELECT * FROM read_parquet('{(papers_dir / "*.parquet").as_posix()}')
            ORDER BY corpusid
        ) TO '{compacting_dir.as_posix()}'
        (FORMAT parquet, COMPRESSION zstd, FILE_SIZE_BYTES '2GB',
         FILENAME_PATTERN '{_CLUSTERED_PREFIX}{generation}_{{i}}')
        """
    )
    connection.execute("SET enable_progress_bar=false")
    shutil.rmtree(spill_dir, ignore_errors=True)
    # The commit point: from here the swap is obligatory and resumable.
    manifest = {"generation": generation, "shards": [pending_file.stem for pending_file in pending]}
    (compacting_dir / _MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    _finish_papers_swap(papers_dir)
    return True


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


def _citations_worker(shard: Path, out_dir: Path) -> None:
    """Ingest one citations shard inside a recycled worker process.

    Runs in the child of the :class:`ProcessPoolExecutor` set up by
    :func:`_ingest_citations_shards` (see :data:`_SHARDS_PER_WORKER` for why
    workers are recycled at all). The connection is cached per process — the
    slowdown being bounded is the process's job, so the connection can live as
    long as its host does.

    Args:
        shard: The input ``.gz`` shard.
        out_dir: ``parquet/citations`` — the partition root.
    """
    global _worker_connection
    if _worker_connection is None:
        _worker_connection = _connect()
    _ingest_citations_shard(_worker_connection, shard, out_dir)


def _ingest_citations_shards(
    connection: duckdb.DuckDBPyConnection,
    shards: list[Path],
    out_dir: Path,
    on_progress: ProgressFn | None,
) -> None:
    """Ingest every pending citations shard, recycling worker processes.

    A run with more pending shards than one worker's quota routes each shard
    through a single-worker :class:`ProcessPoolExecutor` whose child is
    replaced every :data:`_SHARDS_PER_WORKER` shards — the partitioned write
    degrades per *process* (see that constant), so bounding a process's
    lifetime bounds the slowdown. A shorter run (a rerun's tail, the test
    fixtures' two-shard release) can't outlive the same budget in-process, so
    it skips the spawn overhead and uses the caller's connection directly.

    Markers are written by the parent, after the worker returns — completion
    must not be recorded ahead of the rows being on disk.

    Args:
        connection: The parent's DuckDB connection (used only for short runs).
        shards: All of the dataset's downloaded shards, in ingest order.
        out_dir: ``parquet/citations`` — the partition root.
        on_progress: Optional per-shard callback (see :data:`ProgressFn`).
    """
    marker_dir = out_dir / "_done"
    pending_count = sum(
        1 for shard in shards if not (marker_dir / (shard.stem + ".ok")).exists()
    )
    pool: ProcessPoolExecutor | None = None
    if pending_count > _SHARDS_PER_WORKER:
        pool = ProcessPoolExecutor(max_workers=1, max_tasks_per_child=_SHARDS_PER_WORKER)
    try:
        for index, shard in enumerate(shards, start=1):
            if on_progress:
                on_progress("citations", shard.name, index, len(shards))
            marker = marker_dir / (shard.stem + ".ok")
            if marker.exists():
                continue
            if pool is not None:
                pool.submit(_citations_worker, shard, out_dir).result()
            else:
                _ingest_citations_shard(connection, shard, out_dir)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
    finally:
        if pool is not None:
            pool.shutdown()


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

    Incremental: a shard whose output (or ``_done`` marker) already exists is
    skipped, so a rerun resumes after an interruption. Once every papers shard
    is in, the dataset is **compacted** — rewritten globally sorted by
    ``corpusid`` (see :func:`_compact_papers`) — and the arXiv index rebuilt.
    Does **not** flip ``CURRENT`` — the CLI does that only once a full ingest
    succeeds, so the app never reads a half-built release.

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
    from .paths import parquet_root, raw_root, release_paths

    # Ingest is the one operation that needs BOTH halves: it reads shards from the
    # raw root and writes Parquet to the parquet root.
    for key, root in (("raw", raw_root()), ("parquet", parquet_root())):
        if root is None:
            raise CorpusError(f"config.storage.s2.{key} is not set — nothing to ingest")
    paths = release_paths(release_id)
    connection = _connect()

    # papers first (citations don't depend on it, but the arXiv index does, and
    # ordering keeps a combined run's index fresh before anything queries it).
    for dataset in sorted(datasets_wanted, key=lambda name: name != "papers"):
        raw_dir = paths.raw_dataset(dataset)
        shards = sorted(raw_dir.glob("*.gz"))
        if not shards:
            raise CorpusError(f"no downloaded {dataset} shards under {raw_dir}")
        out_dir = paths.parquet_dataset(dataset)
        if dataset == "papers":
            # Land any compaction interrupted mid-swap BEFORE the skip checks
            # below: until the swap completes, its shards have neither a marker
            # nor a per-shard file, and re-ingesting them would duplicate rows
            # the staged generation already carries.
            _finish_papers_swap(out_dir)
            for index, shard in enumerate(shards, start=1):
                if on_progress:
                    on_progress(dataset, shard.name, index, len(shards))
                # Skip on either record: a per-shard file means ingested but not
                # yet compacted; a _done marker means folded into the clustered
                # dataset (the file itself is gone after compaction).
                marker = out_dir / "_done" / (shard.stem + ".ok")
                if marker.exists() or (out_dir / (shard.stem + ".parquet")).exists():
                    continue
                _ingest_papers_shard(connection, shard, out_dir)
        else:
            # A citations shard's outputs are spread across bucket dirs; a
            # marker file records completion so a rerun can skip it cleanly.
            # Long runs recycle worker processes — see _ingest_citations_shards.
            _ingest_citations_shards(connection, shards, out_dir, on_progress)
        if dataset == "papers":
            compacted = _compact_papers(connection, out_dir)
            if compacted or not (paths.parquet / "arxiv_index").exists():
                log.info("building arXiv index for %s", release_id)
                _build_arxiv_index(connection, paths)

    connection.close()


def compact_release(release_id: str) -> bool:
    """Cluster an already-ingested release's papers dataset, in place.

    The migration path for a release ingested before compaction existed (its
    papers are still one file per shard, nothing prunes, and every citer
    hydration is a full scan) — and the recovery path after an interrupted
    compaction. Needs only the parquet root: unlike a re-ingest, the raw shards
    can be long gone. Safe to rerun; an already-clustered release is a no-op.

    Args:
        release_id: The ingested release to compact.

    Returns:
        Whether anything was compacted (False when already fully clustered).

    Raises:
        CorpusError: When the parquet root is unset or the release has no
            ingested papers Parquet.
    """
    from .paths import parquet_root, release_paths

    if parquet_root() is None:
        raise CorpusError("config.storage.s2.parquet is not set — no corpus to compact")
    paths = release_paths(release_id)
    papers_dir = paths.parquet_dataset("papers")
    if not papers_dir.exists():
        raise CorpusError(
            f"release {release_id} has no ingested papers Parquet under {papers_dir}"
        )
    connection = _connect()
    try:
        compacted = _compact_papers(connection, papers_dir)
        if compacted:
            log.info("rebuilding arXiv index for %s", release_id)
            _build_arxiv_index(connection, paths)
    finally:
        connection.close()
    return compacted
