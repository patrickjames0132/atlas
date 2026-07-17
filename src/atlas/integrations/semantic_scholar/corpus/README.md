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

Two roots, one per half — they have opposite access patterns and can want
different drives (`config.storage.s2.raw` / `.parquet`; point both at one
directory if a single drive holds everything):

```
<storage.s2.raw>/                      the downloads — write once, read once
  releases/<release_id>/
    raw/{papers,citations}/*.gz        <- downloaded shards
    download.json                      <- per-shard download checkpoint

<storage.s2.parquet>/                  what gets queried
  CURRENT                              <- text file: the active release_id
  releases/<release_id>/
    parquet/papers/clustered_*.parquet <- projected paper rows, globally SORTED by corpusid
    parquet/papers/_done/<shard>.ok    <- per-shard markers (shard files fold away on compaction)
    parquet/arxiv_index/*.parquet      <- arxiv_id → corpusid (small, sorted)
    parquet/citations/bucket=<N>/…     <- edges, hash-partitioned on citedcorpusid
```

**`CURRENT` sits with the Parquet, not the shards** (v5.7.0): it names an
*ingested* release, so it belongs beside the data it points at. The payoff is that
the parquet root is the app's **only serving dependency** — delete the shards after
an ingest, or unplug that drive entirely, and graph builds carry on. `raw` is
purely an operator concern. `download.json` likewise lives with the shards it
tracks, so discarding a raw root discards its checkpoint too, and a later
re-download starts clean rather than trusting a record of files that are gone.

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

The two halves want opposite storage: `raw/` is ~400 GB read once, sequentially
(fine on a spinning disk), while the Parquet is the queried working set and takes
the ingest's ~400k partitioned writes (measured: **20.6s/shard on NVMe vs 98.2s on
an SMR HDD** — 2.2h vs 10.6h per release). `paths.release_paths(release_id)` wires
both roots from config — **build `ReleasePaths` through it**, never by hand, or the
root you forget stays None and raises only when something touches it.

### Ingest layout, chosen for the one query (`ingest.py`)

The app runs exactly one shape of query: *a single seed's citers, ranked*. Three
choices make that cheap against billions of rows:

- **citations are hash-partitioned on `citedcorpusid`** (`citedcorpusid % NBUCKETS`,
  `NBUCKETS = 1024`). A seed lookup filters to `bucket=<seed % 1024>`, reading
  ~1/1024 of the edge list. Within a bucket, rows are sorted by `citedcorpusid`,
  so Parquet row-group zone maps skip most of the bucket too. **The query side
  imports `NBUCKETS` — the modulus must never be re-hardcoded.**
- **papers are clustered — globally sorted by `corpusid`** (since v5.12.0).
  Shards land one file each (the incremental resume unit), then a **compaction
  pass** rewrites the whole dataset in one `ORDER BY corpusid` sort
  (`clustered_*` files replace the shard files; `_done/` markers keep the rerun
  skip working). Global matters: every shard spans the whole 0–290M id range, so
  per-shard sorting leaves every row group covering everything and *nothing
  prunes* — measured before the fix, hydrating 63 citers cost the same 33s as
  hydrating all 31,878, because every one of the dataset's 1,946 row groups said
  "maybe". Clustered, row groups own contiguous id slices and a small `IN`
  lookup reads a handful of them (subset-measured 1.65s → 0.65s, and the subset
  understates the full-scale win ~30x). The one-time sort is paid once per
  release and took **~10–15 minutes** on the real 24.8 GB — the 1.8 GB subset
  extrapolated to ~3, but it sorted in RAM, and the full dataset spills
  (`_spill/`) into an external merge sort, so DuckDB's progress bar is enabled
  to show movement. The swap is
  staged in `_compacting/` and committed by its `MANIFEST.json`, so a crash at
  any point resumes cleanly. Athena prunes on the same statistics, so the
  endgame layout is unchanged.
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

The buckets exact a second, sneakier price: the partitioned write **slows down
as its host process ages** — ~3x across the first full release (26.5 →
76 s/shard), which benchmarking pinned to the process itself, not to anything
you'd guess first. The same shard-sized COPY repeated in one process degraded
3.04x in 8 minutes with its output *deleted* every iteration; it survived a
DuckDB reconnect without a blip, wasn't the tree (writes into the real 400k-file
corpus cost the same as into an empty dir), wasn't thermal (CPU perf counters
flat), wasn't Defender (0 CPU), and spared single-file COPYs of the identical
sorted+compressed payload — leaving allocator/heap wear from the 1024
per-partition writers as the survivor, and a fresh process demonstrably starting
at cold speed every time. So long citations runs route shards through a
**single-worker process pool recycled every `_SHARDS_PER_WORKER` shards**
(sawtooth-verified: each child starts at cold speed for ~0.3s respawn cost);
runs with no more pending shards than one worker's quota stay in-process, which
keeps the tests and a resumed run's tail spawn-free. Full story in
`docs/bugs.md`.

Ingest is **incremental/idempotent**: both datasets record `_done/<shard>.ok`
markers (a citations shard's output is spread across bucket dirs; a papers
shard's file folds away into the clustered dataset at compaction — so for both,
file existence alone can't tell). A papers shard is also skipped while its
pre-compaction `.parquet` still sits there. A rerun after an interrupted ingest
resumes, and an already-clustered rerun skips the sort too.

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
landmark tests fail if you do. See **Upstream** in `docs/bugs.md`.

### The query seam (`source.py`)

`CitationSource` is a tiny `Protocol` — `landmark_citers(corpus_id, limit, *,
max_landmark_year, landmark_budget=None)` and `latest_bands(corpus_id, *,
band_start, current_year, per_year)` — so the DuckDB-over-Parquet impl now and
the **Athena-over-S3** impl later (same SQL, same schema) are interchangeable and
the app never learns which it's using. `latest_bands` does in **one** windowed
query (`ROW_NUMBER() OVER (PARTITION BY year …)`) what the OpenAlex path needs
one HTTP call per year for — the one place being local is an outright advantage
rather than a workaround.

**Both queries are two-phase since v5.12.0** — rank narrow, hydrate winners:

1. **Rank** joins the seed's (deduped) citer edges to `papers` projecting only
   `(corpusid, year, isinfluential)`, ordered by the citers' citation counts.
   The ranking genuinely must touch every citer, so what it *projects* is the
   whole cost — and the old one-phase query projected all nine display columns
   for every one of them. Measured on DQN (31,878 citers to ship 63): 39.24s,
   of which the `authors` JSON blob alone was +18.6s; the same join projected
   narrow is **1.09s**.
2. **Hydrate** fetches the wide columns (`title`, `authors`, …) for the winners
   only — after the landmark budget has trimmed the ranking, so tens of rows —
   via an `IN` lookup that the clustered layout makes zone-map-prunable. (This
   is the phase that was pointless before clustering: on the arrival-ordered
   layout, 63 ids cost the same full scan as 31,878.)

The edge's `isinfluential` rides through phase 1 and is stitched back on in
Python; `latest_bands` re-sorts its hydrated winners by date in Python to keep
the one-phase query's `publicationdate DESC NULLS LAST` order.

`citation_relations(seed_paper, seed_ref, …)` is the module-level entry point
`services/graph/build.py` calls. It:

1. gets the active source (`active_source()` → None when the corpus is off/absent),
2. resolves the seed to a `corpusid` (arXiv index, or a `CorpusId:<n>` re-seed),
3. **landmarks** — the all-time giants up to `max_landmark_year`, citation-ranked,
   the prefix's length *computed* by the injected `landmark_budget` rule,
4. **latest** — per-year bands from the injected `band_start` rule up to the
   current year, each holding that year's top `latest_per_year`, with anything
   already shipped as a landmark excluded,

returning the same `(landmark, latest)` shape as the live `s2.citation_relations`,
or **None** at any miss so the caller falls back to the live path.

**Since v5.11.0 this path is shaped like the OpenAlex one, not the live one.** It
used to mirror the live fallback's rolling 12-month window, on the reasoning that
the s2 provider's split should mean the same thing whichever source answered — but
that was the wrong symmetry to keep. The live path is a **recency sliver** with no
all-history ranking, so it bands its landmarks and can't place a frontier; the
corpus and OpenAlex both hold whole histories and can. Two of three paths now
agree, and the odd one out is the one that structurally cannot join them. Choosing
the corpus therefore changes *which* citers appear (the true top-cited across all
history) **and** *where the frontier starts* — per-seed, rather than a flat twelve
months. Measured on the real corpus: Hawking's bands start 2020 (7 bands, widened
back to meet a cluster running to 2024), DQN's start 2023 (a tight 4-year frontier,
where the flat span would have said 2020).

**Since v5.11.0 this path computes its landmark budget rather than predicting it.**
`build.py` injects `budget.computed_cite_limit` as a `landmark_budget` rule, the
ranking runs **unlimited**, and the rule measures the full pool — the trained
`cite_budget` model is not consulted here at all. The rule now travels *into*
`landmark_citers` so it runs between the two phases: it reads every ranked
citer's year (nothing pre-trimmed — the whole v5.11.0 point), and only the
prefix it keeps is hydrated wide. Unlimited ranking is cheap because the narrow
projection is the cheap one; the old one-phase query made "unlimited vs 63" a
0.9% difference only because *both* paid the full 20–40s wide join. (This was
the release that left the model serving OpenAlex alone; v5.13.0 finished the
job — the same rule being prefix-local means OpenAlex can compute it from one
ranked page, and the model serves no path at all. See
[`docs/predict-vs-compute.md`](../../../../../docs/predict-vs-compute.md)'s
epilogue and `ml_pipelines/live_pool_validation`'s verdict.)

**The answer is still a count, and the band still a prefix** — the same shape the
model predicted, and the same shape OpenAlex ships. Only its provenance changed,
from an estimate to a measurement: DQN gets **63** where the model said 60, Hawking
**176** where it said 160 (the model's training label *is* this rule, so the two
agree in distribution — mean 75.9 vs 76.5 across the study's 58 seeds — while
differing by ~21 on any given seed).

The live fallback's banded *selector* is deliberately **not** used here, and the
distinction is the subtlest thing in the budget code. A prefix of a **whole-history
ranking** is precisely what a Field Landmark is — the giants — and Latest widens
back to meet the cluster. Banding would instead force `PER_YEAR_CAP` nodes out of
*every* year, admitting the best of a thin 1970 over the 13th-best of a blockbuster
year, and it would flatten the year distribution the tau rule needs to place the
Latest band start. The live path bands because its pool is a **recency sliver**
with no all-time ranking to prefix. Same cap, same invariant, different pools,
different rules.

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
atlas corpus ingest                       # JSONL.gz → Parquet (incl. clustering), flip CURRENT
atlas corpus compact                      # cluster a release ingested before v5.12.0
atlas corpus activate                     # (re)point CURRENT at a finished release
```

`compact` is the **migration** for a corpus ingested before clustering existed
(new ingests compact automatically): a one-time in-place sort of the active
release's papers — ~10–15 minutes; watch DuckDB's progress bar — needing only
the parquet root, so the raw shards can be long gone. Rerunning it on a
clustered release is a fast no-op.

Point `config.storage.s2.raw` and `.parquet` at drives **outside the repo** first
(e.g. `{"raw": "E:\\s2corpus", "parquet": "D:\\s2corpus"}`, or the same directory
twice if one drive holds everything); leave `parquet` `null` and the app just uses
the live S2 path. `download` needs only `raw`, `activate` only `parquet`, `ingest`
both.

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
that emitted nodes satisfy the `Node` model. The clustering gets its own
coverage: the compacted layout and its global sort, an idempotent rerun (same
generation files — no re-sort), the legacy-layout migration through
`compact_release`, and an interrupted swap landing *before* the shard loop can
re-ingest rows the staged generation already carries. No network, no real
Datasets pull.
