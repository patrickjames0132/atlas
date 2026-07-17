# Predict or compute? — models vs. banding in the citation budgets

A design question Patrick raised (2026-07-16) while revisiting the S2 live
fallback: *why does the live path band landmarks per year while OpenAlex uses
the cite-budget model — shouldn't we just train an S2-specific model? And why
band Latest Publications at all instead of predicting its size and density
too?* Working through it produced a principle the next budgeting decision
should reuse, so it's written down here.

This page is the **why**. For the *what* — precise definitions of every term
below (pool, reachable, label, the two rules, `tau`, the three senses of
"anchor"), each with a worked example — see
[`landmark-vocabulary.md`](landmark-vocabulary.md). Companion tickets live in
[`../OnePager.md`](../OnePager.md) (Backlog → Citations & graph data: the
corpus-models ticket and the live-path age-origin ticket); the history
behind the examples is in [`history.md`](history.md) (v4.5.0, v4.6.0, v5.5.0)
and [`bugs.md`](bugs.md).

## One rule, two regimes

Everything in the landmark budget serves one invariant: **don't let any one
publication year flood the graph past a legible cap (`PER_YEAR_CAP` = 12)**.
The apparent inconsistency between the paths — a trained model here, explicit
per-year banding there — is that same invariant enforced in two regimes, and which
regime applies is dictated by the provider's API, not by taste:

- **Predict (OpenAlex).** Landmarks come from a server-side
  `cites:…&sort=cited_by_count:desc&limit=N` query, so N must be chosen
  *before any citer is fetched*. Running the rule exactly would mean
  downloading the seed's whole citer list (130k for DQN) just to throw most of
  it away. This is the one place a prediction earns its keep: the
  `cite_budget` model estimates, from two cheap seed features (age,
  log-citations), where the **STOP rule** *would* stop. Its training label is
  literally that rule — "how many ranked citers before a single year overflows
  K=12" — so on a ranked pool, top-N with a well-chosen N **is** the per-year cap,
  learned rather than enforced. "Don't fetch a pool just to size a trim" is the
  model's whole rationale.
- **Compute (live S2).** S2's `/citations` endpoint has no server-side sort,
  so the build must page the entire reachable list regardless (to the list's
  end or the 9,000-citer ceiling). By selection time the full pool is in
  memory — and once it is, running the rule exactly is free
  (`budget.select_landmarks`, the **SKIP rule**: admit up to `PER_YEAR_CAP` per
  year, most-cited first within each, stepping over years already full).
  **Predicting what you can compute exactly is strictly worse**: you inherit the
  model's error and save nothing. That is why
  "train a new cite-budget model on S2 API pools" is a non-starter — it would
  be a predictor whose entire training distribution is available, in full, at
  serve time, every time. A model is only worth training when the decision
  needs inputs that won't be in hand at the moment of decision.

The asymmetry Patrick noticed is therefore real, but it tracks a real
asymmetry in the two APIs — OpenAlex sells sorted queries, live S2 sells an
unsorted feed — not an inconsistency in the design.

**The corpus is a "compute" path too.** The offline corpus serves ranked
all-history pools (so the model's premise *holds* there, unlike the truncated
live pool) — but the data is local DuckDB, where a per-year grouped selection
is as cheap as a top-N. The corpus-models ticket's re-collection may well
conclude that the corpus should also run the rule exactly, leaving the model
serving only the one path that genuinely can't compute: OpenAlex.

## Why Latest is banded, not predicted

Two reasons, one structural, one measured:

- **A scalar can't express a distribution.** "Ship 40 latest nodes" doesn't
  say *where in time they go*, and recency and citation count are inversely
  correlated (new papers haven't had time to accumulate citations), so any
  single ranking over the recent window collapses to one of its ends — all
  boundary-year papers or all last-month papers. "Every recent year gets a
  fair slice" is inherently a distribution, not a number. The v5.5.0
  landmark hole ("a count can't express the answer" — a top-N prefix over a
  truncated pool stranded 2024–2025 entirely) is the same lesson on the
  other relation. The citation-velocity backlog ticket is the one live
  attempt at a self-balancing *single* ranking; that's why it's filed as a
  candidate **within-band** ranking, not a replacement for bands.
- **The pure-model version was tried and failed.** The `latest_gap` study
  (v4.6.0) fit a regression on seed age + log-citations to predict the Latest
  band start and scored **negative cross-validated R²** — "seed features
  can't predict the boundary" is a written finding
  (`research/latest_gap/analyze.ipynb`). What won was a rule with two
  *learned constants*: `tau=0.25` / `max_span=7` were fit offline on
  misdate-robustness, and `bands.earliest_band_year` runs the rule exactly on
  the actual landmark year distribution at serve time.

## The house pattern

| Situation | What we do |
|---|---|
| The decision must be made **before** the data exists (OpenAlex's fetch N) | **Predict it** — a trained model on cheap seed features (`ml_pipelines/`) |
| The full distribution is **in hand** at serve time (live S2 pool; arguably the corpus) | **Run the rule exactly** — per-year banding, no model |
| The rule has tunable constants (`tau`, `max_span`, the cap of 12) | **Fit them offline** from data — never hand-pick |

One sentence: *learn constants offline, execute rules online, predict only
what you can't observe.* This is the precise form of the repo's
"data-driven over magic numbers" principle — a trained model is not the only
data-driven artifact; a rule whose constants were fit from data is equally
data-driven and, where the distribution is local, strictly more accurate.

## Receipts

- [`bugs.md`](bugs.md) → "The cite-budget model was sizing a pool it was
  never trained on" — what happens when a prediction is applied to a
  distribution it wasn't trained on (and could have been replaced by exact
  computation).
- [`history.md`](history.md) → v4.5.0 (the model and its rationale), v4.6.0
  (the latest-gap rule and the negative-R² finding), v5.5.0 (the live path
  switched from predicting to computing, and why a count can't express the
  answer).
- [`landmark-vocabulary.md`](landmark-vocabulary.md) — every term used above,
  defined once with worked examples.
- `src/atlas/services/graph/budget.py` (`select_landmarks`, `PER_YEAR_CAP`,
  `compute_features`) and `bands.py` (`earliest_band_year`) — the two rules
  as shipped.
