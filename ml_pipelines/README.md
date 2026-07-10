# `ml_pipelines/` — offline model training

Training pipelines that produce models the **app** then loads and serves. Each
pipeline pulls data, fits a model, and writes an artifact under
`ml_pipelines/models/`; the running app loads that artifact and calls
`.predict()`. Nothing here runs inside the app or the request path — it's tooling
you run on demand to (re)produce a model.

```
ml_pipelines/
  cite_budget/   — the adaptive landmark-budget model (graph.adaptive_cite_limit)
  models/        — committed trained artifacts (*.joblib) + metadata.json sidecars
```

## The dependency direction

**Pipelines depend on the app; the app never depends on the pipelines.** A
pipeline imports `atlas` for two things: the data-source clients (e.g. the
throttled OpenAlex client) and — crucially — the **feature contract** (the app's
`compute_features`), so the matrix a model is trained on is built the exact same
way as the vector it's later asked to predict on. That's what keeps train/serve
skew out. The app only ever reaches the other way by *loading a file* from
`models/` — never by importing training code.

## Running a pipeline

The training libs (`scikit-learn`, `joblib`, `numpy`) are app **runtime**
dependencies (the app loads the model), so no extra group is needed to train:

```bash
uv run python -m ml_pipelines.cite_budget.train            # fit from committed data
uv run python -m ml_pipelines.cite_budget.train --refresh   # re-pull data, then fit
```

The committed artifact under `models/` is what ships, so a fresh checkout serves
predictions without anyone having to train first. Retraining on a schedule (to
counter data drift) is deliberately left for later — for now it's a manual run.

## Layout of a pipeline

Each sub-package is self-contained with its own README:

- `collect.py` — pull a labelled corpus to a committed `corpus.csv`.
- `features.py` — any training-only label/feature logic (the *serving* features
  are the app's contract, imported from `atlas`).
- `train.py` — fit, cross-validate, and serialize to `ml_pipelines/models/`.
- `README.md` — the question, the method, and which app constant it feeds.

The exploratory write-up that justified a pipeline's approach lives separately in
`research/` (Jupyter notebooks); `ml_pipelines/` is the productionized, repeatable
fit.
