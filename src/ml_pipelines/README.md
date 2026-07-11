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
  cite_budget/   — the adaptive landmark-budget model (graph.adaptive_cite_limit)
  latest_gap/    — the adaptive latest-band boundary (graph.adaptive_latest_band)
```

Each sub-package holds everything for its model — the collector, trainer, corpus,
README, **and** the committed artifact (`model.joblib` + `model.metadata.json`).
(There is no shared `models/` directory; each model's artifact lives with its
code.)

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
  (`cite_budget` has one for its density label; the *serving* contract always
  lives in `atlas`, imported from there). `latest_gap` needs none — its rule is
  the app's `tail_edge`.
- `train.py` — fit and serialize to `model.joblib` (+ `model.metadata.json`) in
  the same package.
- `model.joblib` / `model.metadata.json` — the committed artifact + its sidecar.
- `README.md` — the question, the method, and which app setting it feeds.

The exploratory write-up that justified a pipeline's approach lives separately in
`research/` (Jupyter notebooks); `src/ml_pipelines/` is the productionized,
repeatable fit.
