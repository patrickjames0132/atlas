# `live_pool_validation` — the age-origin study's collector

The offline validation study behind two Backlog tickets (OnePager → Citations &
graph data): **the live-path age-origin ticket** (run the cite-budget model with
its age feature measured from the oldest *reachable* citer instead of the seed's
publication date — older notes call this "re-anchoring") and the
**corpus-models ticket** (measure whether the model's premise actually holds on
the corpus's full-history pools). One collector serves both because they need the
same thing: a seed's complete, deduped citer set from the offline corpus, measured
two ways.

Unlike its siblings this is a **validation pipeline, not a trainer** — it produces
`corpus.csv` and a verdict (the notebook in `research/live_pool_validation/`), not
a model artifact. Its null hypothesis, stated in the ticket and argued in
[`docs/predict-vs-compute.md`](../../../docs/predict-vs-compute.md), is that the
model is *redundant* on the live path — the pool is already in memory there, so
running the rule exactly beats predicting it. If the verdict instead demands a
retrain, a `train.py` joins this package then.

## Why three columns of the "same" number disagree

Every term here is defined in
[`docs/landmark-vocabulary.md`](../../../docs/landmark-vocabulary.md); this study
imports the app's rules rather than restating them. The one thing you must hold in
your head to read the CSV is that **there are two rules, not one**, and they differ
in a single word.

Both rank a seed's citers most-cited first, drop each into a bucket named by its
publication year, and cap every bucket. What happens when a citer lands on a
**full** bucket is where they part:

```
ranked citer years:  2020  2020  2020  2019  2018  2020  2017    (cap = 2)

STOP   third 2020 overflows  -> quit the walk       => 2
SKIP   third 2020 is skipped -> carry on walking    => 5, spanning 2017-2020
```

Three of this study's columns are those two rules run over different pools:

| column | rule | over which pool |
| --- | --- | --- |
| `citers_before_overflow_reachable` | STOP | the simulated truncated pool (newest ~9k) |
| `citers_before_overflow_full` | STOP | the corpus's full-history pool |
| `selected_up_to_cap_per_year` | SKIP | the truncated pool — what v5.5.0 serves |

So `selected_up_to_cap_per_year` runs several times larger than
`citers_before_overflow_reachable` — **184 vs 63** on average across the collected
corpus. That gap is the two rules, not a bug: STOP quits at the first flooded year
and abandons every sparser year behind it; SKIP steps over and keeps walking. STOP
survives at all only because it returns a scalar and a regression label has to be a
scalar (`budget.py`'s module docstring has the argument, and the 29-vs-84
measurement on DQN).

**A trap worth naming.** `citers_before_overflow_reachable` is *exactly* computed —
but on a pool holding only the newest ~9,000 citers. "Exact" is a claim about the
arithmetic, not about the pool being representative. VMD's reachable label is
**12** against a full-history label of **166**.

## What one row records

For each `cite_budget` seed (the committed 64-seed stratified sample — reused so
the two studies' pools are comparable), the collector:

1. **Simulates the live pool**: the newest `REACHABLE_CITERS` (9,000 — the deep
   pager's own constant, imported from `semantic_scholar.traversal` so it can't
   drift) of the seed's citers, ordered by publication date descending. This is
   the exact truncation the live S2 fallback lives with — DQN's reachable list
   stops at 2019 against a 2013 seed.
2. **Runs both rules on it**: `citers_before_overflow_reachable` (STOP —
   computable at serve time, so it's the null hypothesis's champion) and
   `selected_up_to_cap_per_year` (SKIP — what v5.5.0 ships).
3. **Runs the model from both age origins**:
   `predicted_budget_age_from_oldest_citer` (age measured from the oldest citer in
   the pool — the ticket's proposal) and `predicted_budget_age_from_seed` (age
   from the seed — the pre-v5.5.0 baseline, kept for contrast). Both use the
   committed `cite_budget` artifact and the seed's total citation count.
4. **Labels the full-history pool**: `citers_before_overflow_full` — STOP over the
   corpus's whole citation-ranked citer set (top 500, matching `cite_budget`'s
   `POOL_SIZE`), the corpus ticket's label re-collection.
5. **Places the latest-gap boundary**: `band_start` from `bands.band_start_rule`
   (the fitted tau rule, config-free) on the truncated pool's shipped landmarks —
   the rule was fit on whole-history distributions, so its transfer to truncated
   ones is *checked*, not assumed.

## Running it

Needs the ingested corpus, so it runs **on the corpus machine** (the box whose
`config.storage.s2.parquet` points at the Parquet root):

```bash
uv run python -m ml_pipelines.live_pool_validation.collect
```

The only live traffic is one OpenAlex fetch per seed (the `cite_budget` corpus
stores OpenAlex work ids; the offline corpus resolves arXiv ids and DOIs, so each
work is mapped once through the app's throttled client). Everything else is local
DuckDB. Expect the citer queries to dominate the runtime — a bucket read currently
opens ~390 Parquet footers (the "cold corpus builds take ~54s" backlog ticket), so
~60 seeds is on the order of an hour.

Seeds the corpus can't resolve (no arXiv id and no DOI match — e.g. a seed whose
canonical record is journal-only *and* absent) are skipped with a log line; the
notebook reports how many survived. The 2026-07-16 run resolved **58 of 64**.

## Caveats baked into the simulation

- **Ordering approximation:** S2's live citer list is "newest-first" by an opaque
  internal order; the simulation uses `publicationdate DESC` with undated citers
  last. Where undated citers actually sit in S2's paging is unknowable from
  outside.
- **Row dedupe:** the corpus's edge list carries every edge ~twice (overlapping
  export batches — see `docs/bugs.md` → Upstream); the citer query groups by
  citing paper first, or every pool size in the study would be ~2x.

## Verified by

`test/ml_pipelines/live_pool_validation/` — fully offline: a synthetic corpus
(gzipped JSONL → real ingest → activate, inside `tmp_path`) exercises both
resolution routes (arXiv index, DOI against the papers table), the batch dedupe,
truncation moving the **age origin** (not the seed), and the contract that the
study runs the app's own rule functions rather than private copies.

Note that the collector itself has no test coverage of its live path — the one
OpenAlex call per seed is real traffic, so `collect()` end-to-end is exercised only
by running it.
