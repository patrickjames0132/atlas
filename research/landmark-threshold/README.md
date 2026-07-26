# Landmark threshold — can one citer, read alone, be judged a landmark?

The problem umbrella for this research. Framed 2026-07-25, from scratch —
deliberately without reference to any earlier attempt at this question.

## The problem statement

For a **seed paper** and any of its **citers**, decide whether that citer is a
**landmark** — a paper that matters in its own right.

## Unknowns — named upfront

The problem has two unknowns, and they are not the same size:

1. **What "landmark" means, operationally.** There is no ground-truth label.
   Part of the problem is finding an operational notion of landmark-ness that
   matches what a person exploring the graph would point at and call
   important — and being honest that any such notion is a *choice*, whose
   consequences we measure rather than assume.
2. **What structure in the data supports — or refutes — a single-citer
   judgment.** How citation counts among a seed's citers distribute, how age
   bends what a count means, how much of the variation between seeds is
   predictable from the seed itself, and how much is irreducible.

## Assumptions — stated upfront, each a checkable claim

The framing leans on three beliefs about the domain. None is verified yet;
each is a candidate workstream, and if one fails, the problem re-frames.

- **A1 — Citation counts are heavy-tailed.** Most papers are cited a handful
  of times; a rare few are cited thousands of times. There is no "typical"
  citer, and averages mislead. If true, landmark-ness lives in the far tail.
- **A2 — Raw counts are age-confounded.** An old paper has had more years to
  accumulate citations than a young one, so the same count means different
  things at different ages. Any workable notion of "highly cited" must be read
  relative to age — otherwise "landmark" degenerates into "old."
- **A3 — Seeds live in different citation worlds.** The same citation count
  can be extraordinary among one seed's citers and unremarkable among
  another's. Some observable of the seed carries information about which world
  it lives in.

## Out of scope

- **Productionizing.** Ripping out the current selection rules and wiring
  anything into `src/` is a separate, later process that consumes what we
  learn here. Research ends at understanding.
- **Recategorizing Latest Publications.** If landmark-ness firms up, what
  "latest" means (most recent non-landmarks? a third category for the rest?)
  is a plausibly *separate research problem* — noted here so it isn't lost,
  not studied here.
- **Volume control.** How *many* landmarks a view shows is not this problem;
  this problem is who qualifies, one citer at a time.

## What a valid answer looks like

A described, quantified relationship — with its spread, not just its center.
"Counts among citers fall like *this*, age shifts them like *that*, and a
seed's X predicts Y% of the between-seed variation" is the shape of a good
answer, whatever the values turn out to be.

Degenerate answers are valid answers, and worth watching for from day one:

- **"No single-citer observable separates landmarks from the rest."** Only
  pool-relative ranking works. That would send us past the one-citer-at-a-time
  starting shape and widen the problem — a real finding, not a failure.
- **"A single global bar works everywhere."** The seed contributes nothing;
  A3 is false. The rule collapses to a constant — simpler than anything we'd
  have dared assume.
- **"An assumption fails."** E.g. age barely matters within the pools we
  actually see (A2 fails there), which would delete a whole dimension from the
  problem.

## Workstreams

None yet — they emerge as we explore. Index them here as they open.
