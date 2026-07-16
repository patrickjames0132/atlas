"""Ingest: the arXiv index, the citation hash-partitioning, and idempotent reruns."""

from __future__ import annotations

import duckdb

from atlas.integrations.semantic_scholar.corpus import ingest
from atlas.integrations.semantic_scholar.corpus.ingest import NBUCKETS
from atlas.integrations.semantic_scholar.corpus.paths import release_paths

from .conftest import RELEASE_ID


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
    """A rerun over already-ingested shards is a no-op (skips via existing output
    and the citations _done marker) rather than duplicating rows."""
    paths = release_paths(RELEASE_ID)
    papers_glob = (paths.parquet_dataset("papers") / "*.parquet").as_posix()
    before = duckdb.sql(f"SELECT count(*) FROM read_parquet('{papers_glob}')").fetchone()[0]

    ingest.ingest_release(RELEASE_ID)  # rerun

    after = duckdb.sql(f"SELECT count(*) FROM read_parquet('{papers_glob}')").fetchone()[0]
    assert after == before == 4  # 4 papers, not 8 (no re-ingest)
