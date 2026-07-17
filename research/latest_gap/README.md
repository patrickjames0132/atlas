# `latest_gap` — closing the landmark→latest gap (write-up)

The exploratory notebook behind the adaptive latest-band feature
(`graph.adaptive_latest_band`). It's the **argument**; the shipped, re-runnable
version lives in `ml_pipelines/latest_gap/`, and the app loads the model that
pipeline produces (served by `atlas.services.graph.bands`).

## The question

A seed's *Latest Publications* relation fills recent years evenly, one
`cited_by_count` query per year, over a **fixed** span (`latest_band_years=5`).
For an old seed whose *Field Landmarks* tail off years before that fixed start,
the timeline shows a dead stretch between the last landmark and the first band.
Where should the bands *start*, per seed, so that gap closes?

## What `analyze.ipynb` shows

1. **The gap is real, and old-seed-specific.** 10 of 64 seeds show a ≥ 3-year
   visible gap under the fixed span — all old papers whose landmark cluster ends
   well before the fixed window.
2. **Seed features can't predict the fix.** Reusing the `cite_budget` recipe
   (regress on age + log-citations) scores a CV R² of **−0.15** — negative, i.e.
   worse than predicting the mean. The boundary depends on the *shape* of each
   seed's landmark distribution, not its age/citations. So the model operates on
   the distribution directly — which the build already has in hand (landmarks are
   fetched before the bands).
3. **A quantile is the wrong detector — the old bulk drags it.** The obvious
   "recent edge" statistic is a high quantile of the landmark years, and it was
   the first cut. It *undershoots*: a quantile is **mass**-based, so a seed's
   large old bulk pulls the boundary years before the cluster's visible edge.
   Hawking's landmarks stay dense to **2020** (the cliff you can see on the
   timeline), but its 0.85 quantile sits at **2013** — seven years early, because
   160 landmarks pile up in 2000–2019. What ships instead is the **tail edge**:
   the most recent year whose landmark count is still at least `tau` of the *peak*
   year's count. Being count-based rather than mass-based, it tracks where the
   cluster actually thins rather than where its bulk sits — on Hawking it lands on
   2020, matching the eye.
4. **`tau` is fit on robustness, not gap closure.** Sweeping `tau` barely moves
   gap closure (the `max_span` cap dominates), so it isn't a gap knob — its real
   job is surviving OpenAlex's misdated years. Appending two citers dated two
   years past the newest moves 58/64 seeds' edges at `tau=0.10`, but only **1/64
   at `tau=0.25`** — the cheapest robust choice, and what ships. `max_span=7` is
   a separate cost cap (Patrick's pick): worst case `7 + 2 = 9` per-year band
   queries. There is **no "only widen" clamp** — a young seed starts its bands at
   its own recent edge (QMIX → 2024, three bands); an old one widens back to meet
   its cluster (Hawking → 2020, seven bands).

The notebook reads the corpus from `ml_pipelines/latest_gap/corpus.csv` (the
single copy) and reproduces the analysis inline for the write-up.

## Re-running

```bash
uv run --group research jupyter nbconvert --execute --to notebook \
    --inplace research/latest_gap/analyze.ipynb
```

To re-fit the shipped model from the committed corpus (offline, no API traffic):

```bash
uv run python -m ml_pipelines.latest_gap.train
```

Add `--refresh` to re-pull the corpus from OpenAlex first — that one *does* hit
the live API. Either way, re-execute this notebook afterwards so the write-up
matches. The productionized method, parameters, and tests are documented in
`ml_pipelines/latest_gap/README.md`.
