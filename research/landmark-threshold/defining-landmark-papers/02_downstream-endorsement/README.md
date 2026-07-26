# Loop 02 — downstream endorsement (self-supervised)

## Hypothesis

**A single threshold on a citer's max downstream endorsement separates the
anchor's landmarks from its nots.** Concretely: for each anchor row, take the
citation count of its single largest *downstream* citer (the biggest paper
among the papers citing *it*) — one number per row, computed without ever
consulting a human label. The claim is that this one feature, thresholded,
splits the 6 `landmark` rows from the 135 `not` rows.

The intuition: a paper that matters doesn't just get cited — it gets cited by
papers that themselves get cited. Influence echoes one hop downstream. The
"self-supervised" framing: the signal comes purely from the citation graph;
the hand-labeled anchor only referees it afterward.

Stated caveats, before running:

- **Max-downstream is correlated with raw citation count by construction** — a
  paper with tens of thousands of citers nearly always has a big one among
  them. A pass here does *not* show endorsement adds information beyond the
  raw count; that comparison is a natural next loop.
- **The max is fragile by design** — one routine paper cited once by a
  mega-survey inherits a huge endorsement. If the hypothesis fails, this is
  the likely mechanism, and it would motivate shape-aware variants (e.g. "how
  many downstream citers clear a bar") rather than killing the endorsement
  idea outright.

## Experiment

For each of the 141 decisively-labeled anchor rows (the 15 `unsure` rows sit
out), query the local corpus (release 2026-07-07) for the row's own distinct
citers, and record (a) how many there are and (b) the maximum citation count
among them (0 when it has no citers). Compare the two labeled groups:
distributions on a log scale, the separation structure (lowest landmark vs.
highest not), and the overlap depth (how many nots clear the lowest landmark).

What each outcome means:

- **Clean separation** — downstream endorsement carries the landmark signal
  (with the raw-count-correlation caveat above limiting what that proves).
  The informative output is *where* the gap sits and how wide it is.
- **Overlap** — the max is too fragile (or endorsement genuinely doesn't
  separate); either way the next hypothesis sharpens the feature's shape.
- **Degenerate but valid** — if most nots have zero downstream citers at all,
  the feature "separates" by proxying for having-any-citers, which would say
  the anchor's uniform negatives are too easy for this test and boundary-case
  negatives are needed.

## Results

**Confirmed on this anchor — thin gap, and the caveats outweigh the pass**
(run 2026-07-25, corpus release 2026-07-07; the notebook holds the numbers,
plot, and full interpretation):

- Any threshold in **(6,003 … 7,243]** separates 6/6 landmarks from 135/135
  nots — but that's a 1.21× gap, nearly nothing on a log scale, its location
  weakly determined by six positives.
- The degenerate outcome didn't happen: 114/135 nots have downstream citers
  (median endorsement 13) — the feature isn't a has-citers proxy.
- The stated fragility is real: a 337-citer paper (DAMO-YOLO) carries a 4,820
  endorsement off one big downstream citer. It compresses the gap without
  breaking separation here.
- **The near-boundary `not` is the loop's best find:** the 2008 *Comprehensive
  Survey of Multiagent Reinforcement Learning*, 2,220 citers of its own —
  either a rater-calibration miss (supports the parked multi-rater check) or a
  real definitional question (is a heavily-cited survey a landmark?). Guard:
  it must not be relabeled *because the feature flagged it* — circularity.
  Only independent human judgment may relabel.
- **Free second result: raw citation count also separates this anchor**
  (2,627 vs. 2,220, a 1.18× gap) — so endorsement and raw count are
  **indistinguishable as definitions on this anchor**. Both pass; neither
  with margin.

**What we learned:** with six famous-tier positives, any reasonable bigness
feature separates — this anchor can't yet discriminate between candidate
definitions. The missing data is boundary cases (mid-fame landmarks;
notable-but-not-landmark papers like the survey), which points the workstream
at richer positives — more raters or deliberate boundary-hunting — before
more features.
