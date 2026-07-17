# Live-pool validation — the age-origin verdict

The write-up half of the study whose collector lives in
`src/ml_pipelines/live_pool_validation/` (see that README for what gets collected
and how to run it on the corpus machine). Every term used here is defined in
[`docs/landmark-vocabulary.md`](../../docs/landmark-vocabulary.md) — in
particular **STOP vs SKIP** (the two rules) and **age origin** (what older notes
call "re-anchoring").

`analyze.ipynb` answers three questions from the collected `corpus.csv`:

1. **Does the model with its age origin at the oldest *reachable* citer track the
   STOP rule run exactly on truncated live pools?** If yes, the null hypothesis
   stands: the live path keeps v5.5.0's exact selection and needs no model at all
   ([`docs/predict-vs-compute.md`](../../docs/predict-vs-compute.md) — predicting
   a computable quantity just adds error).
2. **How much worse is the seed age origin** (the pre-v5.5.0 behavior that
   motivated the whole ticket)?
3. **Does the model's premise hold on the corpus's full-history pools?** — the
   corpus-models ticket's measurement (`citers_before_overflow_full` against the
   seed-origin prediction).

Plus an eyeball table of the worked-example seeds' latest-gap `band_start` on
truncated pools — the tau rule was fit on whole-history landmark distributions, so
its transfer is checked, not assumed.

Run it (after `corpus.csv` is collected and committed):

```bash
uv run --group research jupyter nbconvert --execute --to notebook \
    --inplace research/live_pool_validation/analyze.ipynb
```

The notebook fails loudly with instructions when `corpus.csv` hasn't been
collected yet.

## Status

The corpus was collected on the corpus machine **2026-07-16** — 58 of 64 seeds
resolved, 18 of them truncated — and the notebook has been executed against it.
The **Verdict section is still the placeholder framing**: the measured answers are
in the notebook's outputs but the conclusion has not been written, and nothing has
been carried back into the two Backlog tickets. That is the next step, and it's a
judgement call rather than a mechanical one — see the notebook's own Verdict cell
for the outcomes each ticket enumerated.
