# `research/` — exploratory analysis notebooks

The **write-ups** behind data-driven decisions in the app: Jupyter notebooks that
explore a question, justify an approach, and produce the plots that explain *why*
a model or threshold looks the way it does. Nothing here runs in the app or the
quality gate — these are read, not imported.

The split from `ml_pipelines/`:

- **`research/`** (here) — the *exploration*. A notebook compares options, shows
  the evidence, and lands on an approach. It's allowed to be discursive.
- **`ml_pipelines/`** — the *productionized* result. Once a notebook settles an
  approach, the repeatable fit (collect → train → serialize an artifact the app
  loads) lives there as plain modules.

So a study usually appears in both places: the notebook here is the argument; the
pipeline over there is the shipped, re-runnable version.

## Running a notebook

Notebook-only libs (Jupyter, pandas, matplotlib) live in an **opt-in** dependency
group so they never bloat the app's runtime env (scikit-learn / numpy are runtime
deps and always present):

```bash
uv run --group research jupyter nbconvert --execute --to notebook \
    --inplace research/<study>/analyze.ipynb
```

## Layout

```
research/
  cite_budget/       — how the adaptive landmark budget was derived
                       (productionized in ml_pipelines/cite_budget/)
  latest_gap/        — how the adaptive latest-band boundary was derived
                       (productionized in ml_pipelines/latest_gap/)
  citation_coverage/ — S2 vs OpenAlex citation-coverage comparison behind the
                       "could we go OpenAlex-only?" question (no pipeline — pure
                       decision-support; conclusions in docs/citation-coverage.md)
  live_pool_validation/ — do the two trained models survive the live S2 path's
                       truncation to the newest 9000 citers, and does moving the
                       age feature's **age origin** fix the mismatch? (collector
                       in ml_pipelines/live_pool_validation/ — a validation
                       pipeline, no artifact; principle in
                       docs/predict-vs-compute.md)
```

The vocabulary these studies share — landmark, pool, truncated, label, the STOP
and SKIP rules, **age origin**, **worked example** — is defined once in
[`docs/landmark-vocabulary.md`](../docs/landmark-vocabulary.md); a notebook is
allowed to be discursive, but not to redefine a term.

Each study has its own README. Most point at the pipeline they justified, with
corpora and trained artifacts living with the pipeline in `ml_pipelines/` (a
single copy the notebook reads). `citation_coverage/` is the exception — it
justified no model, just a design decision, so it has no pipeline and no stored
corpus (it queries the live S2 + OpenAlex APIs).
