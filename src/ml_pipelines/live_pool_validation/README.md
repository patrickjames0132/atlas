# `live_pool_validation` — the re-anchoring study's collector

The offline validation study behind two Backlog tickets (OnePager → Citations &
graph data): **the live-path re-anchoring ticket** (run the cite-budget model
with its age feature anchored at the oldest *reachable* citer instead of the
seed's publication date) and the **corpus-models ticket** (measure whether the
model's premise actually holds on the corpus's full-history pools). One
collector serves both because they need the same thing: a seed's complete,
deduped citer set from the offline corpus, measured two ways.

Unlike its siblings this is a **validation pipeline, not a trainer** — it
produces `corpus.csv` and a verdict (the notebook in
`research/live_pool_validation/`), not a model artifact. Its null hypothesis,
stated in the ticket and argued in `docs/predict-vs-compute.md`, is that the
re-anchored model is *redundant* on the live path — the pool is in memory
there, so the exact density rule beats any prediction of it. If the verdict
instead demands a retrain, a `train.py` joins this package then.

## What one row records

For each `cite_budget` seed (the committed 64-seed stratified sample — reused so
the two studies' pools are comparable), the collector:

1. **Simulates the live pool**: the newest `REACHABLE_CITERS` (~9k — the deep
   pager's own constant, imported from `semantic_scholar.traversal` so it can't
   drift) of the seed's citers, ordered by publication date descending. This is
   the exact truncation the live S2 fallback lives with — DQN's reachable list
   stops at 2019 against a 2013 seed.
2. **Runs the exact rules on it**: `n_star_live` (the density label,
   `budget.density_budget` — computable at serve time, the null hypothesis's
   champion) and `banded_live` (`budget.density_selection_rule` — what v5.5.0
   ships).
3. **Runs both model anchorings**: `model_pool_anchor` (age from the oldest
   citer in the pool — the ticket's proposal) and `model_seed_anchor` (age from
   the seed — the pre-v5.5.0 baseline, kept for contrast). Both use the
   committed `cite_budget` artifact and the seed's total citation count.
4. **Labels the full-history pool**: `n_star_corpus` over the corpus's whole
   citation-ranked citer set (top 500, matching `cite_budget`'s `POOL_SIZE`) —
   the corpus ticket's `n*` re-collection.
5. **Places the latest-gap boundary**: `band_start` from
   `bands.band_start_rule` (the fitted tau rule, config-free) on the truncated
   pool's shipped landmarks — the rule was fit on whole-history distributions,
   so its transfer to truncated ones is *checked*, not assumed.

## Running it

Needs the ingested corpus, so it runs **on the corpus machine** (the box whose
`config.storage.s2.parquet` points at the Parquet root):

```bash
uv run python -m ml_pipelines.live_pool_validation.collect
```

The only live traffic is one OpenAlex fetch per seed (the `cite_budget` corpus
stores OpenAlex work ids; the offline corpus resolves arXiv ids and DOIs, so
each work is mapped once through the app's throttled client). Everything else
is local DuckDB. Expect the citer queries to dominate the runtime — a bucket
read currently opens ~390 Parquet footers (the "cold corpus builds take ~54s"
backlog ticket), so ~60 seeds is on the order of an hour.

Seeds the corpus can't resolve (no arXiv id and no DOI match — e.g. anchors
whose canonical record is journal-only *and* absent) are skipped with a log
line; the notebook reports how many survived.

## Caveats baked into the simulation

- **Ordering approximation:** S2's live citer list is "newest-first" by an
  opaque internal order; the simulation uses `publicationdate DESC` with
  undated citers last. Where undated citers actually sit in S2's paging is
  unknowable from outside.
- **Row dedupe:** the corpus's edge list carries every edge ~twice (overlapping
  export batches — see `docs/bugs.md` → Upstream); the citer query groups by
  citing paper first, or every pool size in the study would be ~2x.

## Verified by

`test/ml_pipelines/live_pool_validation/` — fully offline: a synthetic corpus
(gzipped JSONL → real ingest → activate, inside `tmp_path`) exercises both
resolution routes (arXiv index, DOI against the papers table), the batch
dedupe, truncation moving the pool anchor, and the contract that the study
runs the app's own rule functions (`density_budget`, `density_selection_rule`)
rather than private copies.
