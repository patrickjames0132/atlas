# Landmark vocabulary — every term, with a toy example

The graph decides two things for every seed: **how many** citers to show as
*Field Landmarks*, and **where in time** the *Latest Publications* bands start.
The code for both is small. The vocabulary around it is not, and several terms
sound like each other while meaning very different things.

This page is the single definition of each term. Everything else — the two code
modules, three ML pipelines, three research notebooks, the integration READMEs —
**links here rather than restating**, so there's one place a definition can
change. If you're reading a term for the first time, read this page first; it
assumes nothing.

The **why** behind these choices lives in
[`predict-vs-compute.md`](predict-vs-compute.md). This page is only the *what*.

---

## The one example everything refers to

Almost every term below is about walking a seed's citers. Here is the walk, with
seven citers and a deliberately tiny cap of 2 (the real cap is 12):

```
The seed's citers, RANKED most-cited first.
Each is labelled with ITS OWN publication year:

  rank:    0      1      2      3      4      5      6
  year:  2020   2020   2020   2019   2018   2020   2017
```

Both rules walk this list left to right, dropping each citer into a bucket named
by its year — the counting-sort image is exact. Both enforce the same invariant:
**no bucket may exceed the cap**. They differ in one word — what happens when a
citer lands on a full bucket.

### Rule 1 — STOP at the first overflow

```
number_of_ranked_citers_before_a_single_year_overflows(years, cap=2)

  rank 0  2020  ->  bucket 2020 = 1   admit
  rank 1  2020  ->  bucket 2020 = 2   admit
  rank 2  2020  ->  bucket 2020 = 3   OVERFLOWS -> STOP THE WALK

  => 2
```

It returns **a count**: how many citers it admitted before quitting. Ranks 3–6
are never looked at, even though buckets 2019, 2018 and 2017 are empty. That
loss is not a bug — it is the defining property, and the reason this rule is
*only* ever used as a training label (see **label** below).

### Rule 2 — SKIP the full bucket and keep walking

```
select_up_to_cap_per_year(years, cap=2)

  rank 0  2020  ->  bucket 2020 = 1   admit
  rank 1  2020  ->  bucket 2020 = 2   admit
  rank 2  2020  ->  bucket FULL       SKIP, keep walking
  rank 3  2019  ->  bucket 2019 = 1   admit
  rank 4  2018  ->  bucket 2018 = 1   admit
  rank 5  2020  ->  bucket FULL       SKIP, keep walking
  rank 6  2017  ->  bucket 2017 = 1   admit

  => [0, 1, 3, 4, 6]
```

It returns **indices**, not a count — the specific citers to ship. Five
landmarks spanning 2017–2020, where Rule 1 stopped at two, both crammed into
2020.

**This is the single most important distinction on this page.** Same cap, same
input, same invariant; one ships a clump, the other ships a spread. Rule 2 is
what the app actually serves. Rule 1 exists only to train a model.

Real numbers, on DQN: Rule 1 stops at 29 landmarks with 2020 full and ships
*nothing from 2024–2025*, leaving an 18-month hole before the Latest frontier.
Rule 2 ships 84 — twelve in each of 2019–2025 — and closes it.

---

## The objects

**seed** — the paper at the centre of the graph. Everything is measured relative
to it.

**citer** — a paper that cites the seed. Note the direction: the seed *has*
citations; each one arrives *from* a citer. When something is "ranked", it means
ranked by the **citer's own** citation count, most-cited first — not by the
seed's.

**pool** — the set of citers a build holds in memory at the moment it decides
what to ship. Whether there *is* a pool is the hinge the whole design turns on
(see [`predict-vs-compute.md`](predict-vs-compute.md)):

| path | has a pool at decision time? | so it must |
| --- | --- | --- |
| OpenAlex | **No** — it pushes `limit=N` into a server-sorted query | **predict** N |
| live S2 | **Yes** — no server-side sort, so it pages everything first | **compute** exactly |
| offline corpus | **No** — it pushes a limit into a ranked DuckDB query | predict (today) |

**landmark** — a citer shipped as a *Field Landmark* node. The claim a landmark
makes is precise: *"one of the most-cited papers to cite this seed **in year
Y**."* A citer with no publication year can't make that claim and is dropped,
not bucketed.

**reachable** — how deep S2's citer feed can actually be paged. Its endpoint
400s past an offset of 8,000 (`_MAX_OFFSET`), and each page holds 1,000, so
8,000 + 1,000 = **9,000 citers** (`REACHABLE_CITERS`) is everything the live
path can ever see, no matter how many exist.

**truncated pool** — a pool cut off by that ceiling. It holds the **newest**
~9,000 citers, so it is a *recency slice*, not a sample. For a mega-cited paper
the slice can be brutally thin: *Attention Is All You Need* has 180,215 citers,
and its newest 9,000 are **all from a single year**. A rule run on a truncated
pool is exact *about that slice* — which is not the same as being right about
the paper.

---

## The two rules, and their cap

**per-year cap** (`PER_YEAR_CAP = 12`) — how many same-year citers a landmark
view tolerates before that year reads as a pile-up. One constant behind both
rules. Fit by sweep, not hand-picked (`research/cite_budget/`).

**`number_of_ranked_citers_before_a_single_year_overflows`** — Rule 1 above. The
STOP rule. Returns a count. **Only ever a training label.** No serving path calls
it. Formerly `density_budget`, and written **`n*`** throughout the older notes.

**`select_up_to_cap_per_year`** — Rule 2 above. The SKIP rule. Returns indices.
This is what ships on the live S2 path. Formerly `density_selection_rule`.

**`select_landmarks`** — the app-facing wrapper around Rule 2: reads the
`graph.adaptive_cite_limit` toggle, applies the `graph.cite_limit` ceiling, logs.
Formerly `density_selection`.

> **Why two functions per rule?** Each rule exists twice — a **pure** version
> that takes its cap as an argument, and a **config-aware** wrapper that reads
> `config.json`. The pure half exists so pipelines and studies can run *the exact
> serving rule* without depending on a local config file. Pure rules are named
> for their mechanics; wrappers are named for their job.

---

## The model side

**label** — the machine-learning sense: the ground-truth value a model is
trained to reproduce. Rule 1's output is the label. It is a **prefix that stops**
purely because a regression target has to be a single number, and the better rule
(Rule 2) returns a list. That's the whole reason a rule everyone agrees is worse
still exists.

**feature** — a model input. There are exactly two (`FEATURE_NAMES`):

- `age` — years from the **age origin** (below) to now, floored at 0.
- `log_cites` — `log10(the seed's citation count + 1)`.

**`predicted_budget`** — runs the trained model's `.predict()` on those two
features and clamps the result. Config-free. Formerly `model_budget`.

**`adaptive_cite_limit`** — the app-facing wrapper: reads the
`graph.adaptive_cite_limit` toggle and `graph.cite_limit` ceiling, then calls
`predicted_budget`. Keeps its name deliberately, matching the config key it
applies.

**age origin** — *which paper's year the `age` feature is measured from.* Two
choices, and the distinction is the whole subject of the `live_pool_validation`
study:

- **from the seed** (`predicted_budget_age_from_seed`) — the seed's own
  publication year. What the model was trained on.
- **from the oldest reachable citer**
  (`predicted_budget_age_from_oldest_citer`) — the oldest year present in the
  truncated pool. Proposed because a truncated pool doesn't span the seed→now
  gap the seed-anchored feature describes: DQN reads as a dense 7-year history,
  not a 13-year classic.

Older notes call the second option **"re-anchoring"**. Prefer "age origin" —
"anchor" is overloaded three ways (below).

**exact / computable** vs **predicted** — "exact" means *computed by running the
rule over a real pool*, as opposed to estimated by the model. It is a claim about
the arithmetic, **not** about the pool being representative. On a truncated pool
both can be true at once: exactly computed, and about the wrong slice.

---

## The Latest-band side

Different model, different module (`bands.py`), same seed.

**band** — one year's worth of *Latest Publications*, filled by its own query.
"Banding" means grouping per year rather than taking a single ranking across the
whole window.

**tail edge** — the recent edge of the landmark cluster: scanning back from the
newest landmark year, the first year whose landmark count is still at least
`tau` of the **peak** year's count. It answers "where does the cluster actually
thin out?"

**`tau`** (`0.25`) — the fraction of the peak a year must reach to still count as
part of the cluster. Scale-free, so it works on a 30-landmark seed and a
160-landmark one alike. Fit on **misdate-robustness**, not on gap closure:
appending two citers dated two years into the future moves 58/64 seeds' edges at
`tau=0.10`, but only 1/64 at `tau=0.25`.

**`max_span`** (`7`) — a pure cost cap: the band start never reaches back more
than 7 years before the landmark cutoff, so an ancient seed can't spawn dozens of
throttled per-year queries. Worst case `7 + 2 = 9` band queries.

**`band_start`** — the first year the bands cover: the tail edge, floored by
`max_span`. There is **no "only widen" clamp** — a young seed starts at its own
recent edge.

**`MIN_LANDMARK_YEARS`** (`10`) — below this many dated landmark years the edge is
too noisy to trust, and the seed falls back to the fixed span.

**Why a rule with fitted constants, not a model?** Predicting the boundary from
seed features was tried and scored a **negative** cross-validated R² (−0.15) —
worse than guessing the mean. The boundary depends on the *shape* of each seed's
landmark distribution, which age and citation count don't capture. So: learn the
constants offline, run the rule online.

---

## "Anchor" means three unrelated things

The worst word in the codebase. Always disambiguate:

1. **A worked-example paper.** The four seeds carried through every study —
   Hawking Radiation, DQN, QMIX, *Attention Is All You Need* — kept so a
   number that looks absurd gets caught before any aggregate hides it. In the
   corpora this is the **`is_worked_example`** column (formerly `is_anchor`).
2. **The age origin.** Where the model's `age` feature is measured from (above).
   Older notes say "re-anchoring". This has **nothing** to do with sense 1.
3. **Force-graph node pinning.** Pure homonym, frontend only
   (`frontend/src/graph/hooks/`) — fixing a node's position on the canvas.
   Nothing to do with citers, budgets, or models.

---

## Where each term lives in code

| Term | Defined in |
| --- | --- |
| Rule 1, Rule 2, `PER_YEAR_CAP`, `predicted_budget`, `adaptive_cite_limit`, features | `src/atlas/services/graph/budget.py` |
| `tail_edge`, `tau`, `max_span`, `band_start`, `MIN_LANDMARK_YEARS` | `src/atlas/services/graph/bands.py` |
| `REACHABLE_CITERS`, `_MAX_OFFSET` | `src/atlas/integrations/semantic_scholar/traversal.py` |
| `UNBOUNDED_LANDMARK_CAP` (500) | `src/atlas/integrations/openalex/` |
| The label corpus + the fitted model | `src/ml_pipelines/cite_budget/` |
| The fitted `tau` / `max_span` | `src/ml_pipelines/latest_gap/` |
| The truncated-pool study | `src/ml_pipelines/live_pool_validation/` |

## A note on older names

Entries in [`history.md`](history.md) are version-tagged records of what shipped
at the time and deliberately keep the **old** names — `density_budget`,
`density_selection`, `DENSITY_CAP`, `n*`, `is_anchor`. They are correct *there*.
This table maps them:

| Old name | Current name |
| --- | --- |
| `density_budget`, `n*` | `number_of_ranked_citers_before_a_single_year_overflows` |
| `density_selection_rule` | `select_up_to_cap_per_year` |
| `density_selection` | `select_landmarks` |
| `model_budget` | `predicted_budget` |
| `DENSITY_CAP` | `PER_YEAR_CAP` |
| `is_anchor` | `is_worked_example` |
| "re-anchoring" | choosing the **age origin** |
