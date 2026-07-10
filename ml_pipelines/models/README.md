# `ml_pipelines/models/` — trained model artifacts

The serialized output of the training pipelines, **committed** so a fresh
checkout serves predictions without anyone having to train first. Each pipeline
writes two files here:

- **`<name>.joblib`** — the joblib bundle the app loads: the fitted scikit-learn
  estimator plus its feature contract, clamp bounds, and training metadata. This
  is the file `.predict()` is called on.
- **`<name>.metadata.json`** *(sidecar)* — the same metadata in human-readable
  JSON (coefficients, CV score, seed count, training date, sklearn version). The
  app never loads it; it's for eyeballing and for a git diff to show what a
  retrain moved.

## Current artifacts

- **`cite_budget.joblib`** / **`cite_budget.metadata.json`** — the adaptive
  landmark-budget model (`graph.adaptive_cite_limit`), loaded by
  `atlas.services.graph.budget`. Produced by `ml_pipelines/cite_budget/train.py`;
  see that package's README.

## Notes

- **Regenerated, not edited.** Never hand-edit these — rerun the pipeline. The
  git diff on a retrain is the record of what changed.
- **Loaded defensively.** The app tolerates a missing, corrupt, or
  feature-mismatched artifact by falling back to the flat `cite_limit`, so a bad
  or absent model degrades gracefully rather than breaking a graph build.
- **Version skew.** `metadata.json` records the `sklearn_version` the artifact was
  pickled with; if the runtime's scikit-learn diverges far enough that a load
  fails, the graceful fallback kicks in — retrain to refresh the pickle.
