"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Ingest: the arXiv index, the citation hash-partitioning, papers clustering
(compaction, its crash-safe swap, the legacy migration), and idempotent reruns.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json
import shutil

import duckdb

from atlas.integrations.semantic_scholar.corpus import ingest
from atlas.integrations.semantic_scholar.corpus.ingest import NBUCKETS
from atlas.integrations.semantic_scholar.corpus.paths import release_paths

from .conftest import RELEASE_ID, write_gzip_jsonl


def test_ingest_builds_arxiv_index(synthetic_corpus):
    """The arXiv index maps a paper's arXiv id to its corpus id."""
    paths = release_paths(RELEASE_ID)
    index_glob = (paths.parquet / "arxiv_index" / "*.parquet").as_posix()
    rows = duckdb.sql(
        f"SELECT corpusid FROM read_parquet('{index_glob}') WHERE arxiv_id = '1706.03762'"
    ).fetchall()
    assert rows == [(1,)]


def test_citations_partitioned_on_cited_bucket(synthetic_corpus):
    """Edges land in the bucket dir for their citedcorpusid (seed id 1 -> bucket 1).

    Five rows for three distinct edges: the fixture ships a second, overlapping
    export batch the way S2 really does. **Ingest stores what upstream sent,
    verbatim** — it can't dedupe, because a duplicate pair spans two shards and
    each shard is written independently. Collapsing them is the query's job
    (`source._citers`).
    """
    paths = release_paths(RELEASE_ID)
    bucket = 1 % NBUCKETS
    bucket_dir = paths.parquet_dataset("citations") / f"bucket={bucket}"
    assert bucket_dir.exists()
    rows = duckdb.sql(
        f"SELECT count(*) FROM read_parquet('{(bucket_dir / '*.parquet').as_posix()}')"
    ).fetchone()
    assert rows[0] == 5  # 3 edges + 2 re-shipped by the second batch
    distinct = duckdb.sql(
        f"""SELECT count(*) FROM (SELECT DISTINCT citingcorpusid, citedcorpusid
            FROM read_parquet('{(bucket_dir / '*.parquet').as_posix()}'))"""
    ).fetchone()
    assert distinct[0] == 3  # all three edges cite the seed


def test_ingest_is_idempotent(synthetic_corpus):
    """A rerun over already-ingested shards is a no-op (skips via the _done
    markers both datasets now use) rather than duplicating rows — and it does
    not re-sort the already-clustered papers either (same generation files)."""
    paths = release_paths(RELEASE_ID)
    papers_dir = paths.parquet_dataset("papers")
    papers_glob = (papers_dir / "*.parquet").as_posix()
    before = duckdb.sql(f"SELECT count(*) FROM read_parquet('{papers_glob}')").fetchone()[0]
    files_before = sorted(file.name for file in papers_dir.glob("*.parquet"))

    ingest.ingest_release(RELEASE_ID)  # rerun

    after = duckdb.sql(f"SELECT count(*) FROM read_parquet('{papers_glob}')").fetchone()[0]
    assert after == before == 4  # 4 papers, not 8 (no re-ingest)
    # The clustered files carry their compaction's generation in their names, so
    # identical names mean the rerun didn't pay for another global sort.
    assert sorted(file.name for file in papers_dir.glob("*.parquet")) == files_before


def test_papers_end_up_clustered(synthetic_corpus):
    """After ingest the papers dataset is the compacted, corpusid-sorted layout:
    only ``clustered_*`` files (the per-shard file is gone, folded in), a _done
    marker standing in for the shard, no staging left behind — and the rows
    globally ordered by corpusid, which is what lets zone maps prune lookups."""
    paths = release_paths(RELEASE_ID)
    papers_dir = paths.parquet_dataset("papers")
    parquet_names = sorted(file.name for file in papers_dir.glob("*.parquet"))
    assert parquet_names, "no papers parquet at all"
    assert all(name.startswith("clustered_") for name in parquet_names)
    assert (papers_dir / "_done" / "papers000.ok").exists()
    assert not (papers_dir / "_compacting").exists()
    assert not (papers_dir / "_spill").exists()
    ids = [row[0] for row in duckdb.sql(
        f"SELECT corpusid FROM read_parquet('{(papers_dir / '*.parquet').as_posix()}')"
    ).fetchall()]
    assert ids == sorted(ids) == [1, 2, 3, 4]


def test_long_citations_runs_ingest_through_recycled_workers(synthetic_corpus, monkeypatch):
    """A run with more pending shards than one worker's quota routes every shard
    through the recycled-worker pool — same rows, same markers, same layout as
    the in-process path.

    The quota is shrunk to 2 so a 5-shard release spans three worker processes
    (the third mid-quota when the run ends) without slowing the suite down. The
    pool exists because the partitioned write degrades per *process* (~3x over
    the first full release); correctness through the pickling/spawn boundary is
    what this test pins.
    """
    monkeypatch.setattr(ingest, "_SHARDS_PER_WORKER", 2)
    paths = release_paths(RELEASE_ID)
    raw_citations = paths.raw_dataset("citations")
    for existing in raw_citations.glob("*.gz"):
        existing.unlink()
    out_dir = paths.parquet_dataset("citations")
    shutil.rmtree(out_dir)
    shard_count = 5
    for shard_index in range(shard_count):
        write_gzip_jsonl(
            raw_citations / f"many{shard_index:03d}.gz",
            [{"citingcorpusid": 100 + shard_index, "citedcorpusid": 1, "isinfluential": False}],
        )

    progressed: list[str] = []
    ingest.ingest_release(
        RELEASE_ID,
        datasets_wanted=("citations",),
        on_progress=lambda dataset, name, index, total: progressed.append(name),
    )

    assert len(progressed) == shard_count
    markers = sorted(marker.name for marker in (out_dir / "_done").glob("*.ok"))
    assert markers == [f"many{shard_index:03d}.ok" for shard_index in range(shard_count)]
    bucket_glob = (out_dir / "bucket=*" / "*.parquet").as_posix()
    rows = duckdb.sql(
        f"SELECT count(*), count(DISTINCT citingcorpusid) FROM read_parquet('{bucket_glob}', hive_partitioning=true)"
    ).fetchone()
    assert rows == (shard_count, shard_count)


def test_compact_release_migrates_a_legacy_layout(synthetic_corpus):
    """`atlas corpus compact` clusters a release ingested before compaction
    existed — per-shard files, no markers — in place, without the raw shards.

    Simulated by devolving the fixture's release back to the legacy shape:
    the clustered file renamed to its per-shard name, markers removed.
    """
    paths = release_paths(RELEASE_ID)
    papers_dir = paths.parquet_dataset("papers")
    clustered = sorted(papers_dir.glob("*.parquet"))
    assert len(clustered) == 1
    clustered[0].replace(papers_dir / "papers000.parquet")
    (papers_dir / "_done" / "papers000.ok").unlink()

    assert ingest.compact_release(RELEASE_ID) is True

    names = sorted(file.name for file in papers_dir.glob("*.parquet"))
    assert names and all(name.startswith("clustered_") for name in names)
    assert (papers_dir / "_done" / "papers000.ok").exists()
    count = duckdb.sql(
        f"SELECT count(*) FROM read_parquet('{(papers_dir / '*.parquet').as_posix()}')"
    ).fetchone()[0]
    assert count == 4  # migrated, not duplicated
    # A second pass finds nothing pending.
    assert ingest.compact_release(RELEASE_ID) is False


def test_an_interrupted_swap_resumes_before_anything_reingests(synthetic_corpus):
    """A compaction that crashed mid-swap (staged files + manifest present, the
    live dir partially emptied, markers not yet written) is landed by the next
    ingest run *before* the shard loop — so the shard is NOT re-ingested into
    rows the staged generation already carries.

    Simulated by rewinding the fixture's finished swap to its commit point:
    the clustered output moved back into ``_compacting/`` under a fresh
    generation name, its manifest restored, the live dir emptied, markers gone.
    """
    paths = release_paths(RELEASE_ID)
    papers_dir = paths.parquet_dataset("papers")
    clustered = sorted(papers_dir.glob("*.parquet"))
    assert len(clustered) == 1
    compacting_dir = papers_dir / "_compacting"
    compacting_dir.mkdir()
    clustered[0].replace(compacting_dir / "clustered_deadbeef_0.parquet")
    (compacting_dir / "MANIFEST.json").write_text(
        json.dumps({"generation": "deadbeef", "shards": ["papers000"]}), encoding="utf-8"
    )
    (papers_dir / "_done" / "papers000.ok").unlink()

    ingest.ingest_release(RELEASE_ID)  # would re-ingest papers000 if the swap didn't land first

    names = sorted(file.name for file in papers_dir.glob("*.parquet"))
    assert names == ["clustered_deadbeef_0.parquet"]  # the staged generation, no re-sort
    assert (papers_dir / "_done" / "papers000.ok").exists()
    assert not compacting_dir.exists()
    count = duckdb.sql(
        f"SELECT count(*) FROM read_parquet('{(papers_dir / '*.parquet').as_posix()}')"
    ).fetchone()[0]
    assert count == 4  # not 8 — the shard wasn't ingested a second time
