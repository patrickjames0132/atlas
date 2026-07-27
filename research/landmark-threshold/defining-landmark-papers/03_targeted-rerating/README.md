# Loop 03 — targeted re-rating of the high-endorsement nots

## Hypothesis

**The anchor's high-endorsement `not` rows are rater-calibration misses — but
only where the paper is big in its own right.** Concretely: deeper-in-the-field
raters, labeling blind, will recognize the 2008 *Comprehensive Survey of
Multiagent Reinforcement Learning* (2,220 citers of its own) as a `landmark`,
while the three one-big-citer artifacts above the same endorsement line
(DAMO-YOLO, *Optimistic Policy Iteration*, TransOMCS — own counts 337, 97, 98)
stay `not`.

This is loop 02's tie-breaker in disguise. Endorsement and raw citation count
were indistinguishable as definitions on the current anchor; the four nominees
are exactly where they diverge — endorsement flags all four, raw count flags
only the survey. Whichever way the raters rule, the tie moves:

- **Survey relabeled, artifacts not** — the hypothesis confirmed. The anchor
  gains its first boundary positive, the first rater-calibration miss is
  quantified, and the tie breaks **toward raw count** (endorsement's extra
  flags were artifacts).
- **Nothing relabeled** — the original labels were calibrated on these rows
  after all; the boundary stands; the survey question resolves toward
  "heavily-cited surveys still aren't landmarks" (with the caveat that the
  raters, too, have finite depth).
- **Artifacts relabeled too** — the surprise outcome: being touched by one
  giant downstream paper is itself recognizable importance. That would
  vindicate endorsement **over** raw count and genuinely reshape the
  workstream.
- **Decoys relabeled** — any relabels among the decoy rows (below) estimate
  the anchor-wide miss rate, softening loop 01's negatives beyond the four
  nominees.

Provenance of the nominees: the researcher eyeballed loop 02's strip plot and
proposed the ~10³ endorsement line (2026-07-25). The feature *nominated* these
rows; per the circularity guard, only independent human judgment may relabel
them — which is precisely what this loop arranges.

## Experiment — design

A **30-row re-rating sheet**: the 4 nominees embedded among **26 decoys**
drawn uniformly (same id-hash order as loop 01, so the draw is deterministic
and metric-blind) from the remaining 131 `not` rows. Rows shuffled by the same
hash so the nominees don't cluster. Same columns as loop 01's sheet — title,
authors, year, arXiv id — **no citation counts anywhere**.

Protocol, per rater (2–3 coworkers deeper in AI/ML than the original rater):

1. Each rater gets their own copy with an empty label column. **Raters are
   told nothing about how rows were chosen** — a rater who knows four rows are
   nominees will find four landmarks. To them it's just "which of these do you
   recognize as papers that matter?"
2. Same blind rules as loop 01: recognition only; `landmark` / `not` /
   `unsure`; no Google, no Semantic Scholar; arXiv abstract pages allowed.
3. Labels come back as separate per-rater columns, never merged by
   discussion — disagreement is data.

Analysis when the sheets return: relabel rates among nominees vs. decoys,
per-rater and pooled; the four nominees read against the outcome table above.

## The sheet — built 2026-07-26

The notebook beside this README builds `rating-sheet.csv` (the 30 blind rows:
corpusid, arXiv id, year, title, authors, empty `label`/`notes` — no counts, no
seed) and `sheet-key.csv` (the analysis key: nominee flags and seed provenance,
never shown to raters), entirely from loops 01–02's committed CSVs. Two
implementation notes, both argued in full in the notebook:

- **Presentation order deviates from the design's letter to keep its intent.**
  "Shuffled by the same hash" backfires literally: the decoys *are* the 26
  smallest draw-hashes, so the unconstrained nominee hashes sort after them —
  empirically all four would land at positions 27–30, the exact clustering the
  shuffle exists to prevent. The sheet instead orders by a **salted** variant
  of the same hash (`md5("order:" + corpusid)`) — still deterministic and
  metric-blind — which spreads the nominees to positions 1, 7, 13, 24.
- **The draw runs over distinct papers, not anchor rows.** Found while
  building: the anchor's 135 `not` rows are only **123 distinct papers** — ten
  citers were sampled independently under 2–3 seeds (loop 01 sampled per seed;
  big-pool citers overlap). The "131 remaining rows" are 119 distinct
  candidates; drawing over unique ids keeps the sheet duplicate-free and the
  draw even (a twice-sampled paper would otherwise enter the sort twice). The
  nominees themselves are single-seed rows, so their status is untouched —
  but loops 01–02's row-level counts quietly double-counted ten papers, worth
  remembering if a later loop treats the 135 as independent draws.

## Prerequisites — the researcher's side

- Recruit the raters (2–3 coworkers, deeper in the space).
- Settle the licensing question first: outside raters' labels entering the
  repo is the working agreement's trigger to consider MIT → Apache-2.0
  *before* their contributions land.

## Results

The sheet was built (2026-07-26, above), but **recruitment fell through**: the
researcher asked around and the intended coworker raters are too busy. That is
itself a result about the method — targeted re-rating is bottlenecked on
qualified-rater time, the one resource this design couldn't secure (the
licensing prerequisite never became relevant). The loop is **parked, not
dead**: the sheet is deterministic and committed, so if raters materialize
later the experiment runs exactly as designed. Meanwhile the tie-breaker
question moves to a successor loop that re-instruments it through the
*public record* of recognition — pre-existing "influential papers" lists,
syllabi, awards — with this sheet's 30 rows as the lookup target set.
