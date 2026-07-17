# `cite_budget` — training the (retired) landmark-budget model

> **Retired from serving in v5.13.0.** No graph build calls `.predict()`
> anymore — every path now computes the model's own training label directly
> from its real citer pool (the STOP rule turned out to be prefix-local, so
> even OpenAlex's one ranked page holds everything it reads; see
> [`docs/predict-vs-compute.md`](../../../docs/predict-vs-compute.md)'s
> epilogue). The pipeline, corpus, and artifact stay: they are the label's
> derivation record, and `latest_gap`'s collector still uses
> `predicted_budget` to trim its distributions the way v5.12-era builds did.

**What it produces.** `model.joblib` (beside this trainer) — the scikit-learn
model that predicted, from a seed's features, how many landmark citers to ship.

**Why it existed.** A flat landmark budget fits no one: an old classic's
landmarks span decades and read as a map of the field, while a young hot
paper's top citers pile into one or two years — same count, far more clutter.
So the budget was *predicted* from two cheap fields already on a seed node —
publication age and citation count — instead of being a hand-tuned constant,
for the one path that (then) couldn't measure its pool at decision time.

## The pipeline

```
cite_budget/
  features.py          — re-exports the app's feature + label contracts; the K-grid
  collect.py           — pull the labelled corpus from OpenAlex -> corpus.csv
  train.py             — fit LinearRegression, cross-validate, serialize the artifact
  corpus.csv           — the committed corpus (features + label per seed)
  model.joblib         — the fitted artifact the app loads (committed)
  model.metadata.json  — human-readable sidecar (params, metrics, date)
```

Neither the *features* (age, log-citations) nor the *label* is defined here — both
are the app's contract in `atlas.services.graph.budget` (`compute_features`,
`number_of_ranked_citers_before_a_single_year_overflows` / `PER_YEAR_CAP`),
re-exported through `features.py` for this pipeline's use. Training and serving
therefore build the feature vector *and* apply the rule identically; there's one
place each can change, and it changes both sides at once. Every term below is
defined in [`docs/landmark-vocabulary.md`](../../../docs/landmark-vocabulary.md).

The label lived here until **v5.5.0**, on the reasoning that the app only ever
*predicts* it and never computes it. That stopped being true: the **live S2
fallback** trims its landmark band by running the rule directly on the citer pool
it already holds in memory, because the model — fit on all-time-ranked landmarks —
doesn't transfer to that path's recency-capped pool. So the rule moved into
`budget.py` beside the features, and training reads it back. See
`atlas/services/graph/budget.py`'s module docstring for that split.

## Method

1. **Label — the STOP rule**
   (`budget.number_of_ranked_citers_before_a_single_year_overflows`). Rank a
   seed's citers by *their own* citation count — exactly the order the app ships
   landmarks in — then walk down, dropping each into a bucket named by its
   publication year. Stop the instant a bucket would take its 13th citer. The
   label is how many were admitted before that break:

   ```
   ranked citer years:  2020  2020  2020  2019  2018  2020  2017   (cap = 2)

   rank 0  2020  ->  bucket 2020 = 1   admit
   rank 1  2020  ->  bucket 2020 = 2   admit
   rank 2  2020  ->  bucket 2020 = 3   OVERFLOWS -> STOP

   => 2   (ranks 3-6 never looked at, though their buckets are empty)
   ```

   That *is* clutter — it caps how many same-year papers crowd the view — so it's
   a principled label, not a guess. An old classic's citers spread over decades, so
   nothing overflows until deep in the list and the label is large; a young hot
   paper's crowd into one or two years, so the label is small.

   Note the rule **stops** rather than skipping the full bucket and walking on.
   That costs it every sparser year behind the flood, and it's deliberate: a
   regression target has to be a single number. The app's *serving* rule
   (`select_up_to_cap_per_year`) skips instead — see the vocabulary page for the
   side-by-side.
2. **Collect** (`collect.py`). Sample ~60 seeds stratified across publication-year
   × citation-count bands from live OpenAlex (plus the four **worked-example**
   seeds — Hawking Radiation, DQN, QMIX, Attention Is All You Need — flagged
   `is_worked_example`), label each, and write `corpus.csv`.
3. **Fit** (`train.py`). Build the feature matrix through the app's
   `compute_features`, fit `LinearRegression`, score with 5-fold cross-validated
   R², and serialize a joblib bundle (estimator + feature contract + clamp floor
   + metadata) to `model.joblib` beside the trainer, with a human-readable
   `model.metadata.json` sidecar for eyeballing and diffing.

## What the data said (see `research/cite_budget` for the full write-up)

- **Age carries the signal** (Pearson r ≈ 0.84 with the label). The intuition that
  *more citations → a tighter budget* does **not** survive controlling for age —
  the log-citation coefficient comes out mildly **positive** (bigger fields
  spread their citers over more years). What makes a paper like "Attention" feel
  like it needs only ~30 landmarks is its *newness*, not its citation count.
- **Plain-age linear beats a sqrt-age variant for robustness.** The sqrt fit is
  marginally better on CV R² but collapses to ~2 landmarks on the **misdated**
  "Attention" record (OpenAlex reports its year as 2025), whereas plain-age
  predicts a sane ~30 there and reproduces DQN (~60) exactly.

Current fit: 64 seeds, CV R² ≈ 0.68. Anchor predictions **Hawking 160, DQN 60,
QMIX 41, Attention 30** — the exact numbers `metadata.json` records and
`test/atlas/services/test_budget.py` pins.

## Running it

```bash
uv run python -m ml_pipelines.cite_budget.train             # fit from committed corpus.csv
uv run python -m ml_pipelines.cite_budget.train --refresh    # re-pull the corpus first
uv run python -m ml_pipelines.cite_budget.collect            # just refresh corpus.csv
```

`--refresh` re-hits OpenAlex (polite pool, a couple hundred throttled calls).
After a refresh, commit the updated `corpus.csv`, the new `model.joblib` +
`model.metadata.json`, and re-run `research/cite_budget/analyze.ipynb` if you want
the write-up to match.

## The artifact

`model.joblib` / `model.metadata.json` are **committed** so a fresh checkout
serves predictions without training first. The `.joblib` is the bundle the app
loads (the fitted estimator + its contract marker + clamp floor + metadata); the
`.metadata.json` is the same metadata in human-readable JSON (never loaded — for
eyeballing and for a git diff to show what a retrain moved). **Regenerated, not
edited** — never hand-edit them; rerun the pipeline, and the diff is the record.
**Loaded defensively** — a missing, corrupt, or contract-mismatched artifact makes
the app fall back to the flat `cite_limit`, so a bad or absent model degrades
gracefully. **Version skew:** the pickled scikit-learn estimator can fail to load
if the runtime's scikit-learn diverges far enough; the fallback then kicks in —
retrain to refresh the pickle.

## Testing

Offline tests live in `test/ml_pipelines/cite_budget/` — the density-label
function (pure) and a fit-and-serialize smoke test on a tiny synthetic corpus, so
the pipeline is exercised with no network and no dependence on the committed data.
The *served* model's behavior is pinned separately in
`test/atlas/services/test_budget.py`.
