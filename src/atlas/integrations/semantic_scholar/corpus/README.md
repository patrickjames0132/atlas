# `integrations.semantic_scholar.corpus`

The offline Semantic Scholar **citations corpus** — the *real* fix for the s2
provider's recency-biased Field Landmarks.

## Why it exists

Everywhere else the app follows the "never store a paper corpus" bet: it asks S2
live. But S2's **live citation endpoint has a hard limitation** — it returns a
seed's citers newest-first, with no citation-count sort, capped at a ~10k offset
(`traversal._MAX_OFFSET`). So for a heavily-cited paper the *most-cited* (landmark)
citers are older, buried past the ceiling, and simply **unreachable live**. The
s2 provider's landmarks are therefore drawn from the recent ~10k citers and
recency-biased — the known interim limitation documented in
[`../README.md`](../README.md) and [`docs/citation-coverage.md`](../../../../../docs/citation-coverage.md).

There is exactly one fix (option **(b)** in that doc): hold S2's citation graph
**locally** and query your own copy, which finally gives the citation-count sort
the live API never offered. That's this package. It's a deliberate, bounded
exception to the no-corpus rule — the data lives **outside the repo**, on a roomy
drive, gitignored; the app stays corpus-*optional* and falls back to the live
path when it's absent.

## The data

Two bulk **Datasets API** releases (refreshed monthly), current sizes:

| Dataset | Records | Shards | Compressed | What it gives us |
|---|--:|--:|--:|---|
| `citations` | 2.4 B edges | ~390 | ~255 GB | `citingcorpusid → citedcorpusid` (+ `isinfluential`) |
| `papers` | 200 M | ~60 | ~45 GB | `corpusid ↔ externalids` (arXiv/DOI), title, year, date, **citationcount** |

Papers are keyed by S2's integer **`corpusid`**, and citation edges reference
those ids — so answering "who cites this seed, ranked" is necessarily a **join**:
`citations` gives the citer ids, `papers` supplies the counts to rank by and the
external ids to render. Neither dataset alone is enough.

## How it's structured

```
paths.py     — on-disk layout: per-release subtrees + the CURRENT pointer
datasets.py  — the Datasets API client (release id + signed shard URLs) + CorpusError
     ↓
download.py  — resumable, checkpointed shard downloader (URL-expiry-aware)
     ↓
ingest.py    — DuckDB: JSONL.gz → Parquet (papers + arXiv index; citations bucketed)
     ↓
source.py    — the query side: CitationSource seam, DuckDBCitationSource, citation_relations
```

### On-disk layout (`paths.py`)

```
<s2_corpus_dir>/
  CURRENT                              <- text file: the active release_id
  releases/<release_id>/
    raw/{papers,citations}/*.gz        <- downloaded shards (download.json checkpoint)
    parquet/papers/*.parquet           <- projected paper rows, one file per shard
    parquet/arxiv_index/*.parquet      <- arxiv_id → corpusid (small, sorted)
    parquet/citations/bucket=<N>/…     <- edges, hash-partitioned on citedcorpusid

# with s2_corpus_parquet_dir set, the parquet/ half moves (raw/ + CURRENT stay put):
<s2_corpus_parquet_dir>/releases/<release_id>/parquet/…
```

Each release is isolated so a fresh monthly pull downloads and ingests alongside
the live one; only `CURRENT` (flipped by `atlas corpus ingest`/`activate`) decides
which release the app queries.

**That guard has one hole, and it bites:** it protects a release that isn't active
*yet*. Re-ingesting a release `CURRENT` **already** points at — e.g. after a
partial first pass — exposes the half-built state live. Papers ingest first and
rebuild the arXiv index, so seeds start *resolving* against a corpus whose edges
are ~0% ingested, and `citation_relations` returns `([], …)` — a valid tuple, not
`None` — so the build prefers the corpus and ships a graph whose landmarks are a
random sample of whatever shards happen to be done, labelled "corpus". Move
`CURRENT` aside before re-ingesting an active release.

**The Parquet can live elsewhere** (`config.storage.s2_corpus_parquet_dir`),
mirroring the same `releases/<id>/parquet` subtree on another drive. The two halves
want opposite storage: `raw/` is ~400 GB read once, sequentially (fine on a spinning
disk), while the Parquet is the queried working set and takes the ingest's ~400k
partitioned writes (measured: **20.6s/shard on NVMe vs 98.2s on an SMR HDD**).
`paths.release_paths(release_id)` wires both roots from config — **build
`ReleasePaths` through it**, never by hand, or `parquet_root` defaults to None and
the split is silently ignored.

### Ingest layout, chosen for the one query (`ingest.py`)

The app runs exactly one shape of query: *a single seed's citers, ranked*. Two
choices make that cheap against billions of rows:

- **citations are hash-partitioned on `citedcorpusid`** (`citedcorpusid % NBUCKETS`,
  `NBUCKETS = 1024`). A seed lookup filters to `bucket=<seed % 1024>`, reading
  ~1/1024 of the edge list. Within a bucket, rows are sorted by `citedcorpusid`,
  so Parquet row-group zone maps skip most of the bucket too. **The query side
  imports `NBUCKETS` — the modulus must never be re-hardcoded.**
- **an arXiv index** (`arxiv_id → corpusid`, only rows that have an arXiv id)
  makes resolving a seed — nearly always an arXiv paper — a small sorted lookup
  instead of a 200M-row scan.

Those 1024 buckets make one DuckDB setting load-bearing: **`partitioned_write_max_open_files`,
which defaults to 100**. A `PARTITION_BY` spanning more partitions than DuckDB can
hold open must close and reopen them as it cycles — and a closed Parquet file can't
be appended to, so every reopen starts a *new* one. Left at the default, one
citations shard produced **~21k files averaging 3.5 KB** (nearly all footer, no
data), on course for ~8M files per release; file *creation*, not throughput, was the
bottleneck — 2.8 min/shard, ~18h projected, and merely listing the output directory
timed out. `_connect()` raises it past `NBUCKETS`, giving one ~61 KB file per bucket
per shard. **Any change to `NBUCKETS` has to move that limit with it.**

Ingest is **incremental/idempotent**: a papers shard whose `.parquet` exists is
skipped; a citations shard records a `_done/<shard>.ok` marker (its output is
spread across bucket dirs, so existence alone can't tell). A rerun after an
interrupted ingest resumes.

### S2 ships every edge twice (their bug, our GROUP BY)

A release's `citations` dataset comes as **more than one export batch, and the
batches overlap**. `2026-07-07` advertises 390 shards — 240 stamped
`…_00151_3g69z_…` and 150 stamped `…_00016_bxc9g_…` — carrying **5.1B rows for
~2.7B distinct edges**. The download is correct; that's just what S2 lists.

So `_citers` **groups by `citingcorpusid` before the join and the limit**.
Without it a `limit` counts *rows, not papers*: DQN's 63-landmark budget bought
~32 real landmarks (27,230 rows / 13,729 distinct = 1.98x). It hid because
`build.py`'s `add_edge` dedupes endpoints — the graph stayed correct, just
half-empty — and because S2's *API* reports DQN at 13,824 citations, matching the
**distinct** count, so their own two surfaces disagree by 2x.

**It can't be fixed at ingest:** a duplicate pair spans two different shards, and
each shard is written independently, so a per-shard `DISTINCT` never sees both
copies. Ingest stores upstream's rows verbatim; the query collapses them.
`isinfluential` is `bool_or`-ed, because the batches disagree about it. Don't
remove the grouping — the fixture ships an overlapping batch precisely so the
landmark tests fail if you do. See **Bugs → Upstream** in `OnePager.md`.

### The query seam (`source.py`)

`CitationSource` is a tiny `Protocol` — `landmark_citers(corpus_id, limit)` and
`latest_citers(corpus_id, limit)` — so the DuckDB-over-Parquet impl now and the
**Athena-over-S3** impl later (same SQL, same schema) are interchangeable and the
app never learns which it's using.

`citation_relations(seed_paper, seed_ref, …)` is the module-level entry point
`services/graph/build.py` calls. It:

1. gets the active source (`active_source()` → None when the corpus is off/absent),
2. resolves the seed to a `corpusid` (arXiv index, or a `CorpusId:<n>` re-seed),
3. runs the landmark + latest queries and returns the same
   `(landmark, latest)` shape as the live `s2.citation_relations`,

or returns **None** at any miss so the caller falls back to the live path. The
landmark/latest split mirrors the live path's rolling 12-month window
(`_LATEST_WINDOW_MONTHS`), so choosing the corpus changes *which* citers appear
(now the true top-cited across all history), not what the relations mean.

Citer nodes are emitted in the exact `nodes.node()` dict shape (the `Graph` model
forbids extra keys), keyed `id = "CorpusId:<n>"` — which S2 accepts as a
re-seedable external id, and which merges with a live-API sighting of the same
paper through the shared `arxiv_id` in `build.py`'s dedup. A corpus citer has no
abstract/tldr/fields (those are separate datasets), hydrated lazily when the node
is opened.

## The workflow (the `atlas corpus` CLI)

Downloading ~300 GB is an **operator action you run yourself** (hours-to-days,
resumable) — not something on any request path:

```
atlas corpus status                       # where the corpus is, what's downloaded/active
atlas corpus download --shards 1          # a ~1 GB/dataset sample to prove the pipeline
atlas corpus download                     # the full ~300 GB (resumes if interrupted)
atlas corpus ingest                       # JSONL.gz → Parquet, then flip CURRENT
atlas corpus activate                     # (re)point CURRENT at a finished release
```

Point `config.storage.s2_corpus_dir` at a roomy drive **outside the repo** first
(e.g. `E:\s2corpus`); leave it `null` and the app just uses the live S2 path.

## Design decisions worth knowing

- **stdlib-only download** (`urllib`, like the rest of the S2 client) — the shards
  are streamed GETs with a `Range` header; no new HTTP dependency for that.
- **Signed URLs expire.** The Datasets API hands out pre-signed S3 links that
  lapse after hours, so `download.py` never persists them: on a mid-pull 403/416
  it re-lists from `datasets.py` and retries the same (stably named) shard.
- **DuckDB does everything** — reads gzipped JSONL and writes/queries Parquet — so
  there's no pandas/pyarrow step. It's a runtime dependency because the query side
  runs at serve time.
- **A fresh `DuckDBCitationSource` per build**, not a cached singleton — cheap to
  open, and it stays correct when config is repointed (the tests do this).
- **`CorpusError`** is the one exception the pipeline raises, kept separate from
  `S2Error`: this is an offline/operator concern (the CLI), not a per-request
  graph-build one.

## The AWS endgame this prototypes

The DuckDB-over-Parquet impl is the **local prototype** of the long-term shape:
an **Airflow** DAG pulls the monthly release into **S3**, and the app queries it
with **Athena** when the s2 provider is selected. DuckDB SQL over Parquet and
Athena SQL over S3 Parquet are near-identical, and `CitationSource` is the seam,
so that swap is a new implementation class behind the same two methods — no
change to `build.py`.

## Testing

`test/atlas/integrations/semantic_scholar/corpus/` mirrors this package, fully
offline: tiny synthetic `.gz` shards are ingested to a temp corpus dir (the
autouse temp-DB isolation already redirects storage), then queried — asserting
landmark citation-sort, the latest window's oldest-first reveal, seed resolution,
graceful fallback (`citation_relations` → None) when the corpus is absent, and
that emitted nodes satisfy the `Node` model. No network, no real Datasets pull.
