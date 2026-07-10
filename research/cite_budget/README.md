# `cite_budget` — deriving the adaptive landmark budget (write-up)

The exploratory notebook behind the adaptive `cite_limit` feature. It's the
**argument**; the shipped, re-runnable version lives in
`ml_pipelines/cite_budget/`, and the app loads the model that pipeline produces.

## The question

The graph build ships up to `cite_limit` landmark citers per seed. A flat number
fits no one: an old classic's landmarks span decades and read as a map of the
field, while a young hot paper's top citers pile into one or two years — same
count, far more clutter. What's the *right* landmark budget for a given seed, and
can we predict it from fields the build already has?

## What `analyze.ipynb` shows

1. **A data-driven label.** The "density budget" `n*` — the longest **prefix**
   (the first N, from the top) of a seed's citation-ranked citer list in which no
   single year exceeds `K = 12` citers — makes "clutter" measurable, so the
   target isn't eyeballed. (See `ml_pipelines/cite_budget/features.py` for the
   precise walk and a worked example.)
2. **The mechanism.** `n*` falls as citers concentrate in time, and age is what
   spreads them out (Pearson r ≈ 0.84 between `n*` and age). The counter-intuitive
   part: controlling for age, citation count is a mild *positive* term, not the
   negative you'd expect.
3. **Model choice.** A plain-age linear model `n* ~ age + log10(citations)` is
   chosen over a sqrt-age variant because it survives OpenAlex's dating noise (the
   misdated "Attention" record, age 1, predicts ~30 not ~2) while reproducing the
   anchors (Hawking 160, DQN 60, QMIX 41, Attention 30).

The notebook reads the corpus from `ml_pipelines/cite_budget/corpus.csv` (the
single copy) and reproduces the fit inline for the write-up.

## Re-running

```bash
uv run --group research jupyter nbconvert --execute --to notebook \
    --inplace research/cite_budget/analyze.ipynb
```

To refresh the underlying data or the shipped model, use the pipeline
(`python -m ml_pipelines.cite_budget.train --refresh`), then re-execute this
notebook so the write-up matches. The productionized method, coefficients, and
tests are documented in `ml_pipelines/cite_budget/README.md`.
