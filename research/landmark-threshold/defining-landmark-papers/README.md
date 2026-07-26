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
| [01](01_hand-labeled-anchor/README.md) | Landmark-ness is crisp enough for a person to label decisively (few unsures; recalled names really are citers) | Blind, recall-first labeling of 10 known seeds; counts hidden throughout; uniform-random negatives | Recall hit-rate 6/9 — all three misses are lineage-not-citation conflations (one directionally impossible); pool sizes span 476–180k (~380×); blind labeling of 150 sampled citers pending | Recall positives must be corpus-verified before use; human "landmark memory" tracks influence, not reference lists |
