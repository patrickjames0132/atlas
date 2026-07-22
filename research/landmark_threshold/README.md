# Landmark threshold — fitting the citation predicate

The write-up half of the study whose pipeline lives in
`src/ml_pipelines/landmark_threshold/` (see that README for the collector, the
trainer, and how to run them on the corpus machine). The design and its reasoning
— why a predicate replaces the four selection rules, the two wrong turns, the two
normalizations — are settled in
[`docs/citation-threshold.md`](../../docs/citation-threshold.md); this notebook is
the *evidence* behind the fitted numbers, not the argument for the approach.

`analyze.ipynb` reads the committed `corpus_s2.csv.gz` and the fitted
`model_s2.metadata.json` and answers:

1. **Does an age curve of the form `T(age) = a·(age+1)^p` fit the data?** Plot the
   empirical per-age citer citation-count quantiles and overlay the fitted curve —
   is a 2-parameter monotone form enough, or does the curve need a per-age table?
2. **Does a single-parameter `S(seed)` hold every seed in the 20–40 band?** — the
   design's stated fitting risk. Plot the achieved landmark-count distribution and
   the spread by seed-size decade. Where do seeds fall out of band, and why?
3. **How do the worked examples land?** Hawking / DQN / QMIX / *Attention* landmark
   counts, eyeballed against the semantic claim (a few dozen field-definers, not
   hundreds).

The S2 curve is fit from the offline corpus (thousands of seeds); the OpenAlex
curve is a separate study (pending), because the two providers' citation counts
are on different scales.

Run it (after `corpus_s2.csv.gz` is collected and `model_s2.joblib` is fit and
committed):

```bash
uv run --group research jupyter nbconvert --execute --to notebook \
    --inplace research/landmark_threshold/analyze.ipynb
```

The notebook fails loudly with instructions when the corpus or the artifact hasn't
been produced yet.

## The verdict (first fit, 2026-07-21 — 1,502 seeds, S2 release `2026-07-07`)

**1. The age curve form is fine.** `T(age) = a·(age+1)^p` tracks the empirical
per-age citer quantiles; nothing suggests a per-age lookup table would buy
anything. The fitted `p` is stable around 0.55–0.80 and `beta` around 0.66–0.69
across every band tried.

**2. A single-parameter `S()` does *not* hold the 20–40 band — and neither would
any other pool-independent rule.** This is open item #2, answered: the answer is
no, and the reason is structural rather than a fitting failure.

The check that settles it: for a fixed `p` and `FLOOR`, a seed's landmark count
depends on the rule only through the single multiplier `m = a·(seed/median)^beta`,
because a citer is admitted iff `m <= cited_by/(age+1)^p`. So each seed has an
*exact interval* of multipliers that put it in band, and "can this form hold the
band?" becomes "does a line through `(log seed_size, log m)` stab those 1,502
intervals?" — exhaustively searchable over the whole model family.

| | |
|---|---|
| ceiling for this form (any `a, p, beta, FLOOR`) | **~35%** in band |
| what the fit achieved | 31.6% — within 3 points of the ceiling |
| seeds individually reachable at *some* multiplier | 99.5–100% |
| residual scatter of the required multiplier | **1.9× (1σ)** |
| width of the 20–40 target | **1.65×** |

The target interval is narrower than the irreducible scatter. Ruled out
explicitly: a more flexible `S()` (per-decade medians are already centered at
35 / 42 / 30 — the miss is *within*-decade scatter, not bias); a second
pool-independent predictor (adding the seed's own age moves R² 0.782 → 0.786 and
in-band coverage not at all); and any `p`/`FLOOR` (ceiling varies only 29–35%
across the sweep).

**The R² is a trap worth recording.** Seed size explains 79% of the required
multiplier overall — but that is almost entirely *between* size cohorts (big seeds
need big bars, trivially). *Within* a cohort it collapses: R² = 0.17 for
1k–10k-cite seeds, 0.19 for ≥10k, 0.10 for ≥30k. Seed citation count buys a coarse
"bigger seed, higher bar" and essentially nothing else. Where the bar belongs is a
property of the *citer distribution's shape* — field, community, era — which no
seed-level feature sees.

**3. The worked examples overflow, and the biggest seeds are the hardest.** At a
10–80 band: Hawking 32, QMIX 54 (in band), but DQN 88 and *Attention* 114 (over).
That is not the fit neglecting four seeds — big seeds are *intrinsically* worse
behaved (residual scatter 2.10× for ≥10k cites and 2.19× for ≥30k, against 1.75×
below 1k). Since users explore famous papers far more than a stratified sample
implies, the cohort the rule serves worst is the one it will be judged on.

### What this means for the design

A predicate reads one citer and never the pool — the whole justification for the
rip-out. But a landmark **count** is a pool property. A pool-independent rule can
*center* the count distribution; it cannot *pin* it per seed. The two goals are in
direct tension, and this study measures the exchange rate.

Achievable in-band fractions (real fits, not projections):

| band | in-band | median count | Hawking / DQN / QMIX / *Attention* |
|---|---|---|---|
| 20–40 | 31.6% | 35 | 26 / 94 / 56 / 137 |
| 15–60 | 55.5% | 44 | 32 / 89 / 55 / 108 |
| 10–80 | 73.7% | 42 | 32 / 88 / 54 / 114 |
| 10–100 | 76.6% | 52 | 43 / 112 / 61 / 142 |

If an exact count guarantee is wanted, it belongs in the **display layer** — where
the sliders already cap what is drawn, and where pool-dependence is harmless
because it touches neither traversal nor caching — not in the predicate, where it
would cost the order-free property the rip-out was for.
