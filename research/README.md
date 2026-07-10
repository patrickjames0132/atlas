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
  cite_budget/   — how the adaptive landmark budget was derived
                   (productionized in ml_pipelines/cite_budget/)
```

Each study has its own README pointing at the pipeline it justified. Corpora and
trained artifacts live with the pipeline in `ml_pipelines/`, not here — the
notebook reads them from there so there's a single copy.
