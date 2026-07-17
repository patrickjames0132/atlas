# `src/ml_pipelines/` — offline model training

Training pipelines that produce models the **app** then loads and serves. Each
pipeline pulls data, fits a model, and writes its artifact (`model.joblib` +
`model.metadata.json`) **beside its own code**; the running app loads that
artifact and calls `.predict()`. Nothing here runs inside the app or the request
path — it's tooling you run on demand to (re)produce a model.

It lives under `src/` as a second top-level package alongside `atlas`, but it is
**not** part of the shipped app package (`[tool.hatch.build.targets.wheel]` ships
only `src/atlas`) — it's importable in the dev env because the editable install
puts `src/` on the path.

```
src/ml_pipelines/
  cite_budget/   — the landmark-budget model (retired from serving in v5.13.0 —
                   every path now computes its STOP-rule label directly; the
                   artifact remains the label's derivation record and a
                   latest_gap-collector dependency)
  latest_gap/    — the adaptive latest-band boundary (graph.adaptive_latest_band)
  live_pool_validation/ — validation only: both models measured against the live
                   S2 path's truncated pools, simulated from the offline corpus
```

Each sub-package holds everything for its model — the collector, trainer, corpus,
README, **and** the committed artifact (`model.joblib` + `model.metadata.json`).
(There is no shared `models/` directory; each model's artifact lives with its
code.) `live_pool_validation/` is the one exception to "produces an artifact":
it's a **validation** pipeline — collector + committed corpus + a verdict
notebook in `research/`, no trainer unless its findings demand one.

The vocabulary all three share — landmark, pool, truncated, label, the STOP and
SKIP rules, **age origin**, **worked example** — is defined once in
[`docs/landmark-vocabulary.md`](../../docs/landmark-vocabulary.md). Read that
before a pipeline README.

## The dependency direction

**Pipelines depend on the app; the app never depends on the pipelines.** A
pipeline imports `atlas` for two things: the data-source clients (e.g. the
throttled OpenAlex client) and — crucially — the **shared contract**, the
serving-side function that decides how inputs map to a prediction (`cite_budget`
imports the app's `compute_features`; `latest_gap` imports the app's `tail_edge`
rule). Training builds on that same function, so the model is fit exactly the way
it's later served. That's what keeps train/serve skew out. The app only ever
reaches the other way by *loading a file* from a pipeline's package — never by
importing training code.

## Running a pipeline

The training libs (`scikit-learn`, `joblib`, `numpy`) are app **runtime**
dependencies (the app loads the model), so no extra group is needed to train:

```bash
uv run python -m ml_pipelines.cite_budget.train            # fit from committed data
uv run python -m ml_pipelines.cite_budget.train --refresh   # re-pull data, then fit
```

The committed `model.joblib` in each package is what ships, so a fresh checkout
serves predictions without anyone having to train first. Retraining on a schedule
(to counter data drift) is deliberately left for later — for now it's a manual run.

## Layout of a pipeline

Each sub-package is self-contained with its own README:

- `collect.py` — pull a labelled corpus to a committed `corpus.csv`.
- `features.py` — any training-only label/feature logic, when a pipeline needs it
  (`cite_budget` has one, but it only *re-exports* the app's features and its
  **STOP rule** label and adds a training-only cap grid; the *serving* contract
  always lives in `atlas`, imported from there). `latest_gap` needs none — its
  rule is the app's `tail_edge`.
- `train.py` — fit and serialize to `model.joblib` (+ `model.metadata.json`) in
  the same package.
- `model.joblib` / `model.metadata.json` — the committed artifact + its sidecar.
- `README.md` — the question, the method, and which app setting it feeds.

The exploratory write-up that justified a pipeline's approach lives separately in
`research/` (Jupyter notebooks); `src/ml_pipelines/` is the productionized,
repeatable fit.
