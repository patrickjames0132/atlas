# Workstream: defining landmark papers

**Theme.** What is a landmark, operationally? This workstream attacks the
problem's unknown #1 directly: before any threshold can be studied, "landmark"
needs a meaning that doesn't collapse into circularity ("landmark = highly
cited, and look — citation counts find landmarks"). Every other workstream this
problem will ever have measures *against* some notion of landmark-ness; this
workstream is where candidate notions are proposed and stress-tested.

**The anchor.** The workstream's external ground truth is a **hand-labeled
set**: the researcher labels the landmarks among the citers of 10–12 seed
papers they know deeply, *without seeing citation counts* — so the labels
encode human judgment of influence, not an echo of the metric under study.
Every candidate definition earns credibility by agreement with this set (and
loses it by disagreement someone can articulate). The anchor is **AI/ML-only
by construction** — the researcher's expertise lives there — so agreement with
it validates a definition for AI/ML, and nothing further (assumption A4 in the
problem README).

**Candidate angles** — each a source of hypotheses for this workstream's loops:

- **Supervised agreement** — a candidate definition's picks vs. the hand
  labels: precision/recall against human judgment.
- **Declared definition** — "exceptional citation record for its context (age,
  field's world)" made quantitatively precise, with its consequences measured
  rather than assumed.
- **Self-supervised endorsement** — a citer judged by its *own* citers: does
  having large citers downstream of you separate landmarks better than your
  raw count does?
- **Unsupervised structure** — does the citer pool cluster naturally (e.g.
  clustering with silhouette scoring) into a "landmark-shaped" group without
  any labels, or is the pool one smooth continuum?

## Loops

| # | Hypothesis | Experiment | Results | What we learned |
|---|---|---|---|---|
| [01](01_hand-labeled-anchor/README.md) | Landmark-ness is crisp enough for a person to label decisively (few unsures; recalled names really are citers) | Blind, recall-first labeling of 10 known seeds; counts hidden throughout; uniform-random negatives | Recall hit-rate 6/9 (all misses lineage-not-citation, one directionally impossible); 150 blind labels: 0 recognized, 135 within-field `not`, 15 out-of-field `unsure`; pools span 476–180k (~380×); anchor built (6/135/15) | Recall positives must be corpus-verified; landmarks are ≲2% (plausibly ≪1%) of a uniform citer draw; decisive ≠ calibrated — rater strength is the open question, multi-rater check proposed |
| [02](02_downstream-endorsement/README.md) | A threshold on max downstream endorsement (biggest paper citing the citer) separates the 6 landmarks from the 135 nots | Compute the feature from the citation graph alone for all 141 labeled rows; anchor referees | Separates 6/6 vs 135/135, but the gap is thin (6,003→7,243, 1.21×); raw citation count also separates (1.18×) — the two are indistinguishable here; best find: a 2,220-citer RL survey labeled `not` sits at the boundary | Famous-tier positives make any bigness feature pass — the anchor needs boundary cases (mid-fame landmarks, notable non-landmarks) before it can discriminate between definitions; surveys pose a definitional question of their own |
