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

## Experiment — design (not yet run)

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

## Prerequisites — the researcher's side

- Recruit the raters (2–3 coworkers, deeper in the space).
- Settle the licensing question first: outside raters' labels entering the
  repo is the working agreement's trigger to consider MIT → Apache-2.0
  *before* their contributions land.

## Results

Pending — the loop stops at this write-up by design (2026-07-25, end of
session); the rater sheet is the next session's first move.
