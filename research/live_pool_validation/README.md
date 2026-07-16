# Live-pool validation — the re-anchoring verdict

The write-up half of the study whose collector lives in
`src/ml_pipelines/live_pool_validation/` (see that README for what gets
collected and how to run it on the corpus machine). `analyze.ipynb` answers
three questions from the collected `corpus.csv`:

1. **Does the re-anchored cite-budget model** (age measured from the oldest
   *reachable* citer, not the seed) **track the exact density label on
   truncated live pools?** If yes, the null hypothesis stands: the live path
   keeps v5.5.0's exact banded selection and needs no model at all
   (`docs/predict-vs-compute.md` — predicting a computable quantity just adds
   error).
2. **How much worse is the seed-anchored baseline** (the pre-v5.5.0 behavior
   that motivated the whole ticket)?
3. **Does the model's premise hold on the corpus's full-history pools?** — the
   corpus-models ticket's measurement (`n_star_corpus` vs the seed-anchored
   prediction).

Plus an eyeball table of the anchors' latest-gap `band_start` on truncated
pools — the tau rule was fit on whole-history landmark distributions, so its
transfer is checked, not assumed.

Run it (after `corpus.csv` is collected and committed):

```bash
uv run --group research jupyter nbconvert --execute --to notebook \
    --inplace research/live_pool_validation/analyze.ipynb
```

The notebook fails loudly with instructions when `corpus.csv` hasn't been
collected yet. The Verdict section is written against the outcomes the two
Backlog tickets enumerate — fill it in with the measured answer, then carry
the conclusion back into the tickets.
