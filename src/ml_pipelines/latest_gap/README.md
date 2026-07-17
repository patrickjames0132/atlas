# `latest_gap` — fitting the adaptive latest-band boundary

**What it produces.** `model.joblib` (beside this trainer) — the model the app
loads (`atlas.services.graph.bands`) to decide, per seed, where the *Latest
Publications* per-year bands should **start** (replacing the fixed
`config.graph.latest_band_years` span).

**Why.** Field Landmarks are a seed's all-time most-cited citers (any year);
Latest Publications fills recent years evenly, one `cited_by_count` query per
year, over a fixed 5-year span (2020-2024 today). For an *old* seed whose
landmark cluster tails off years before that fixed start, the timeline shows a
dead stretch between the last landmark and the first band — the gap this closes.

## The pipeline

```
latest_gap/
  collect.py           — pull each seed's shipped-landmark year distribution -> corpus.csv
  train.py             — fit the tail-edge threshold tau, serialize the artifact
  corpus.csv           — the committed corpus (year distributions per seed)
  model.joblib         — the fitted artifact the app loads (committed)
  model.metadata.json  — human-readable sidecar (params, metrics, date)
```

The seeds are **reused from `cite_budget`** (same 64 stratified seeds incl. the
four **worked examples** — the `is_worked_example` corpus column), and each seed's
landmark pool is trimmed to the served `cite_budget` budget, so the study describes
exactly the landmarks a build would ship. The *tail-edge rule itself* is not
defined here — it's the app's contract,
`atlas.services.graph.bands.tail_edge`, imported by `train.py`, so training and
serving can't disagree on what the boundary means. Every term below — **band**,
**tail edge**, `tau`, `max_span`, **landmark**, **worked example** — is defined
once in [`docs/landmark-vocabulary.md`](../../../docs/landmark-vocabulary.md).

## Method

1. **Collect** (`collect.py`). For each `cite_budget` seed, pull the top citers by
   citation count capped at the landmark-era cutoff (`openalex.landmark_max_year`),
   trim to the served budget (`budget.predicted_budget`), and record their publication
   years. Write `corpus.csv`.
2. **Fit** (`train.py`). The rule starts the bands at the **tail edge** of a
   seed's landmark years — scanning back from the newest, the first year whose
   count is still ≥ `tau` of the peak year's count — floored so the start reaches
   back at most `max_span` years
   (bounded query cost). `train.py` fits `tau` on **misdate-robustness** (see
   below) and pins `max_span` (a cost choice), then serializes a joblib bundle
   (params + rule contract + metrics) to `model.joblib` beside the trainer, plus a
   `model.metadata.json` sidecar.

## What the data said (see `research/latest_gap` for the full write-up)

- **The gap is an old-seed phenomenon.** ~10 of 64 seeds show a ≥ 3-year visible
  gap under the fixed span; they're all old papers whose landmark cluster ends
  well before the fixed start. Young papers already have landmarks reaching it.
- **Seed features can't predict the boundary.** A regression on age + log-citations
  (as the sibling `cite_budget` model uses) scores a *negative* CV R² — the
  boundary is a property of each seed's landmark **distribution**, not its
  age/citations. So the model operates on the distribution directly.
- **A tail edge, not a quantile.** A quantile is *mass*-based, so a seed's
  large old bulk drags the boundary years before the cluster's visible edge
  (Hawking stays dense to ~2020 but the 0.85 quantile sits at 2013 — the clamp was
  quietly doing all the work). The tail-edge detector tracks where the
  per-year count actually falls off, and there's **no only-widen clamp**: a young
  seed starts its bands at its own recent edge (a tight frontier).
- **`tau` is fit on robustness, not gap closure.** Gap closure is *flat* across
  `tau` (the `max_span` cap dominates), so `tau` is chosen as the smallest
  threshold whose boundary survives a two-citer future misdate on ≥ 95% of the
  corpus — OpenAlex's unreliable years being the arc's recurring hazard. A higher
  threshold needs more same-year citers to move the edge.

Current fit: 64 seeds, **tau=0.25, max_span=7** — worst case 9 band queries
(`max_span + 2`, the two latest-only years always banded up to today), only ~1/64
seeds movable by a misdate. Worked-example edges: Hawking 2020, DQN 2021,
Attention 2022, QMIX 2024 (a young seed, tight). `metadata.json` records the exact
numbers;
`test/atlas/services/test_bands.py` pins the served behavior.

## Running it

```bash
uv run python -m ml_pipelines.latest_gap.train             # fit from committed corpus.csv
uv run python -m ml_pipelines.latest_gap.train --refresh    # re-pull the corpus first
uv run python -m ml_pipelines.latest_gap.collect            # just refresh corpus.csv
```

`collect.py` reads `src/ml_pipelines/cite_budget/corpus.csv` for its seed list and
needs the trained `cite_budget` model (to reproduce each build's landmark trim),
so run the `cite_budget` pipeline first if starting from nothing. A `--refresh`
re-hits OpenAlex (polite pool, a few hundred throttled calls); after one, commit
the updated `corpus.csv`, the new `model.joblib` + `model.metadata.json`, and
re-run `research/latest_gap/analyze.ipynb` if you want the write-up to match.

## The artifact

`model.joblib` / `model.metadata.json` are **committed** so a fresh checkout
serves predictions without training first. The `.joblib` is the bundle the app
loads (the fitted `tau`/`max_span` + rule contract marker + metrics); the
`.metadata.json` is the same in human-readable JSON (never loaded — for eyeballing
and diffing). **Regenerated, not edited** — rerun the pipeline rather than editing
them. **Loaded defensively** — a missing, corrupt, or contract-mismatched artifact
makes the app fall back to the fixed `latest_band_years` span, degrading
gracefully. (This model pickles no estimator — just fitted numbers — so it's free
of the scikit-learn version-skew hazard the `cite_budget` pickle carries.)

## Testing

Offline tests live in `test/ml_pipelines/latest_gap/` — the visible-gap metric
(pure) and a fit-and-serialize smoke test on a tiny synthetic corpus, so the
pipeline is exercised with no network and no dependence on the committed data.
The *served* model's behavior is pinned separately in
`test/atlas/services/test_bands.py`.
