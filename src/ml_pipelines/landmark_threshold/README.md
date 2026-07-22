# `landmark_threshold` — fitting the citation predicate

**What it produces.** `model_s2.joblib` (beside the trainer) — the three fitted
constants of the one-line rule that splits a seed's citers into **Landmarks** and
**Latest Publications**:

```
is_landmark(citer) = citer.cited_by >= max(FLOOR, T(now - citer.year) * S(seed))

  T(age)  = a * (age + 1) ** p                    # the age curve, monotone in age
  S(seed) = (seed.cited_by / median_seed) ** beta  # the seed scale, S(median) = 1
```

**Why it exists.** The design in
[`docs/citation-threshold.md`](../../../docs/citation-threshold.md) replaces four
pool-shaped selection rules (STOP / SKIP / prefix / band) with a single
**predicate** that reads *one* citer and never the pool — so it is order- and
provider-independent by construction. A predicate needs no pool ranking, but it
does need calibrated constants: how many citations a citer of a given **age** must
have to count as a landmark, scaled by how large the **seed** itself is. Those
constants — `a`, `p`, `beta`, `FLOOR` — are what this pipeline fits.

Two motivations are baked into the shape:

- **Maturity** — a young citer hasn't had time to accrue citations, so the bar
  rises with the citer's age (`T(age)`). Indexing on *age*, not calendar year,
  keeps the curve stationary: "a 5-year-old paper needs ~N citations to stand out"
  stays true next year without a refit.
- **Dynamic range** — a niche seed's citers are all low-cited and a blockbuster's
  all high-cited, so an absolute bar would leave the niche graph empty and flood
  *Attention*. `S(seed)` scales the bar by the seed's own citation count, which is
  known before any citer is fetched — so the rule stays order-free and still pushes
  into a SQL `WHERE`.

`FLOOR` binds at the recent end (a two-month-old paper's age-bar would be ~2
citations, which is no landmark). Recent years fall below it wholesale, so
**"Latest" is the complement by construction** — a 2025 citer sits in Latest,
accrues citations, crosses the floor, and becomes a Landmark on its own, no re-fit.

## Two curves, one per provider

S2 and OpenAlex report different citation counts for the same paper (different
indexing coverage), so a curve fit on one miscalibrates the other. Calibration
therefore uses **two curves**, each pinning `S(median seed) = 1` on its own scale:

- **`T_s2[]`** — fit here, from the offline S2 citations corpus. Thousands of
  seeds, local, free (`collect_s2.py` / `train_s2.py`). **Done.**
- **`T_openalex[]`** — a sibling collector/curve, fit from a throttled live
  OpenAlex run (~64 seeds). **Pending** — lands beside this one, not in a new
  package.

## The pipeline (S2 half)

```
landmark_threshold/
  collect_s2.py          — sample seeds + their citer (year, cited_by) distributions
                           from the corpus via DuckDB -> corpus_s2.csv.gz
  train_s2.py            — fit (a, p, beta, FLOOR) to the 20–40 band, report spread,
                           serialize the artifact
  corpus_s2.csv.gz       — the committed corpus (long format, one row per citer bin)
  model_s2.joblib        — the fitted constants the app's predicate loads (committed)
  model_s2.metadata.json — human-readable sidecar (constants + achieved spread)
  README.md              — this file
```

Unlike `cite_budget`, the *rule* here is fitted **constants**, not a scikit-learn
estimator — the predicate is arithmetic. So there is no shared `compute_features`
contract to re-export; the serving-side predicate (Phase 2, `services/graph`) reads
the same `model_s2.joblib` constants and applies the formula above.

## Method

1. **Collect** (`collect_s2.py`). Sample ~75 seeds per `(publication-year ×
   citation-count)` stratum from the corpus (plus the four **worked examples** —
   Hawking / DQN / QMIX / Attention), and for each seed record its citers as
   `(citer_year, citer_cited_by, count)` bins. That histogram is lossless for
   landmark counting — the predicate classifies each citer from its own age and
   citation count — so the fit never re-queries the corpus. Citers below
   `PRUNE_FLOOR = 2` citations (never a landmark) and undated citers (no age) are
   dropped from the rows but kept in the `total_citers` denominator.

   The whole run accumulates in memory and writes **once**, at the end, so the
   write step is the risky one: it is UTF-8 explicitly (a Unicode hyphen in a seed
   title once sank an hour-long run against Windows' cp1252 default), and titles
   are kept only for the worked examples. `TestCorpusRoundTrip` covers both.

   Sampling is by **hash order** (`ORDER BY hash(corpusid, seed) LIMIT n`), not
   DuckDB `USING SAMPLE`: the latter's reservoir terminates on the first row group
   of the `corpusid`-clustered scan and draws only the lowest ids (measured: max id
   ~1.2M of 288M). Hash-ordering spans the pool and reproduces for a fixed seed.

2. **Fit** (`train_s2.py`). Flatten the corpus into arrays and minimize a **per-seed
   band penalty** — zero when a seed's landmark count is inside 20–40, growing
   outside — over `(a, p, beta, FLOOR)`. Overflow always costs; a shortfall costs
   only when the seed even *has* 20 eligible citers (a 12-citer niche seed isn't
   penalized for shipping 12). The search is a vectorized coarse grid then
   coordinate descent — no scipy, because a count-based penalty is non-smooth and
   the space is only 4-D. `S(median seed) = 1` is pinned by dividing every seed by
   the sample median. `FLOOR >= PRUNE_FLOOR` is enforced so the pruned corpus never
   understates a count.

## The objective — a composition target, not a volume one

**Target: 20–40 landmarks per seed** (Patrick, 2026-07-20). This is *not* how many
nodes the graph draws — the always-visible **sliders** govern that (display-only).
The threshold governs only the **split**: tightening the landmark count reclassifies
citers from Landmark into Latest, it doesn't shrink the graph. 20–40 leaves room for
both halves to show at the default slider position, and matches the semantic claim
— *Attention* has ~180k citers, and the field-defining ones (BERT, GPT-3, ViT, …)
number a few dozen, not the ~76 the retired cite-budget model averaged.

**Report the achieved spread, not just the parameters.** A single-parameter `S()`
holding *every* seed inside a 2× band across three orders of magnitude of seed size
is the design's stated fitting risk. So `train_s2.py` prints the achieved landmark
distribution — the in-band fraction, the spread by seed-size decade, and the four
worked-example counts.

### The first fit says 20–40 is not reachable (2026-07-21)

It came in at **31.6% in band**, and that is within 3 points of the **~35% ceiling
for the entire model family** — not an optimizer failure. The required per-seed
multiplier scatters **1.9× (1σ)** around anything seed size can predict, while the
20–40 band is only **1.65×** wide. A more flexible `S()`, a second
pool-independent predictor, and every `p`/`FLOOR` were each ruled out explicitly.

The tension is structural: a predicate reads one citer and **never the pool** —
the whole reason for the rip-out — but a landmark *count* is a pool property. The
rule can center the count distribution; it cannot pin it per seed. Widening is the
lever that works (10–80 → 73.7%). The evidence, the cohort breakdown, and the
band-vs-coverage table are in
[`research/landmark_threshold/`](../../../research/landmark_threshold/README.md).

**The band is Patrick's call** (design open item #2) — the artifact in this package
is still fitted to the design's stated 20–40 until that decision lands.

## Running it

```bash
uv run python -m ml_pipelines.landmark_threshold.collect_s2    # refresh corpus_s2.csv.gz (corpus machine)
uv run python -m ml_pipelines.landmark_threshold.train_s2       # fit from the committed corpus
uv run python -m ml_pipelines.landmark_threshold.train_s2 --refresh   # re-collect, then fit
```

Collection runs **only on the corpus machine** (`config.storage.s2_corpus` set) and
takes ~1.5 h (1,502 seeds); fitting runs anywhere the committed `corpus_s2.csv.gz`
is present and takes ~15 min (the coarse grid is ~17k evaluations over 1.5M citer
bins). After a refresh, commit the updated `corpus_s2.csv.gz`, `model_s2.joblib`,
and `model_s2.metadata.json`, and re-run `research/landmark_threshold/analyze.ipynb`
if you want the write-up to match.

### Why the corpus is gzipped

Its sibling pipelines commit a plain `corpus.csv` of 8–33 KB; this one is ~6 MB
compressed from 67 MB. The difference is real, not sloppiness: the band question
needs a dense sample (1,502 seeds, not a handful), and a seed's citer bins are
dominated by the **wide high-citation tail** — thousands of distinct `cited_by`
values, mostly one citer apiece. Pruning harder barely dents it (at a floor of 50
it is still 37 MB / 824k rows), and the values can't be bucketed because a
hyper-cited seed's bar lands in the tens of thousands, so precision up there is
load-bearing. Gzip is exactly lossless, so `corpus_s2.csv.gz` it is;
`collect_s2.open_corpus` is the one place that knows.

## The artifact

`model_s2.joblib` / `model_s2.metadata.json` are **committed** so a fresh checkout
serves the predicate without fitting first. The `.joblib` is the bundle the app
loads (`provider`, `a`, `p`, `beta`, `floor`, `median_seed`, `age_max`,
`as_of_year`, plus the spread report and provenance); the `.metadata.json` is the
same content in human-readable JSON (never loaded — for eyeballing and diffs).
**Regenerated, not edited** — rerun the pipeline; the diff is the record.

## Testing

Offline tests in `test/ml_pipelines/landmark_threshold/`: the collector's corpus
queries against a synthetic ingested release (`conftest.synthetic_corpus`), the
prune/denominator logic, and the trainer's predicate / band penalty / coarse-to-fine
search on hand-built seeds — no network, no dependence on the committed data or the
real corpus.
