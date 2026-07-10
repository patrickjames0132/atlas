# `cite_budget` — training the adaptive landmark-budget model

**What it produces.** `ml_pipelines/models/cite_budget.joblib` — the scikit-learn
model the app loads (`atlas.services.graph.budget`) to decide how many landmark
citers to ship per seed (`config.graph.cite_limit` becomes the ceiling).

**Why.** A flat landmark budget fits no one: an old classic's landmarks span
decades and read as a map of the field, while a young hot paper's top citers
pile into one or two years — same count, far more clutter. So the budget is
*predicted* from two cheap fields already on a seed node — publication age and
citation count — instead of being a hand-tuned constant.

## The pipeline

```
cite_budget/
  features.py   — the training-only LABEL: density budget n* (density_budget)
  collect.py    — pull the labelled corpus from OpenAlex -> corpus.csv
  train.py      — fit LinearRegression, cross-validate, serialize the artifact
  corpus.csv    — the committed corpus (features + n* label per seed)
```

The *features* (age, log-citations) are **not** defined here — they're the app's
contract, `atlas.services.graph.budget.compute_features`, imported by `train.py`.
Training and serving therefore build the feature vector identically; there's one
place that can change, and it changes both sides at once.

## Method

1. **Label — the density budget `n*`** (`features.density_budget`). For a seed,
   walk its citers ranked by citation count (exactly what the app ships as
   landmarks), counting per publication year; `n*` is the longest **prefix** —
   the first N citers from the top of that ranked list — in which no single year
   exceeds `K = 12` citers. Concretely: admit citers from the top one at a time
   and stop the instant some year would take its 13th slot; `n*` is how many were
   admitted before that break. That *is* clutter — it caps how many same-year
   papers crowd the view — so it's a principled label, not a guess. (The exact
   walk, with a worked example, is in `features.py`'s docstring.)
2. **Collect** (`collect.py`). Sample ~60 seeds stratified across publication-year
   × citation-count bands from live OpenAlex (plus the four working anchors:
   Hawking Radiation, DQN, QMIX, Attention Is All You Need), label each with `n*`,
   and write `corpus.csv`.
3. **Fit** (`train.py`). Build the feature matrix through the app's
   `compute_features`, fit `LinearRegression`, score with 5-fold cross-validated
   R², and serialize a joblib bundle (estimator + feature contract + clamp floor
   + metadata) to `ml_pipelines/models/`, with a human-readable `metadata.json`
   sidecar for eyeballing and diffing.

## What the data said (see `research/cite_budget` for the full write-up)

- **Age carries the signal** (Pearson r ≈ 0.84 with `n*`). The intuition that
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
After a refresh, commit the updated `corpus.csv`, the new `models/` artifact +
`metadata.json`, and re-run `research/cite_budget/analyze.ipynb` if you want the
write-up to match.

## Testing

Offline tests live in `test/ml_pipelines/cite_budget/` — the density-label
function (pure) and a fit-and-serialize smoke test on a tiny synthetic corpus, so
the pipeline is exercised with no network and no dependence on the committed data.
The *served* model's behavior is pinned separately in
`test/atlas/services/test_budget.py`.
