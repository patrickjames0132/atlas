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

## The verdict (2026-07-17)

Collected 2026-07-16 (58 of 64 seeds; 18 truncated), executed, and answered. The
full argument is the notebook's Verdict section; the conclusion is **the model
comes off the live path — and off the corpus path too**, leaving it serving
OpenAlex alone:

- **Q1/Q2.** Moving the age origin to the oldest reachable citer is a **real
  repair** — the seed origin scores **−0.707** on truncated pools (worse than
  guessing the mean), the oldest-citer origin **+0.446**. But the repaired model
  is still **41% off** a number the live path computes exactly, for free, from
  memory. Validated, and unneeded.
- **Q3.** The premise **holds** — R² **0.644** on corpus pools against the model's
  own **0.680** on its training pools. It still shouldn't be used there: timed on
  DQN, the corpus's `LIMIT` saves **0.9%** of a 22-second query (22.08s for 63
  citers vs 22.28s for all 28,732). The pool is already paid for and thrown away.
- **Band starts.** The tau rule is **structurally incompatible** with a
  quota-selected band — 56/58 seeds collapse to a one-year band, and 23/23 of the
  exactly-flat ones do. It belongs on the corpus path instead.
- **Unasked-for.** "Exact" is about arithmetic, not the pool: VMD's live label is
  **12** against a full-history **166**.

Both tickets are updated: the live-path one is resolved in
[`docs/history.md`](../../docs/history.md), and the corpus one is re-scoped around
the measurement in [`OnePager.md`](../../OnePager.md).
