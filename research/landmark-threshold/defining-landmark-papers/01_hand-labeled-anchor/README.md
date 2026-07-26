# Loop 01 — the hand-labeled anchor

## Hypothesis

**Landmark-ness is crisp enough for a person to label decisively.** Concretely:
blind, recall-first labeling of 10–12 seeds the researcher knows deeply will
produce (a) few "unsure" labels, and (b) recalled landmark names that
overwhelmingly turn out to actually be citers of their seed.

This is the workstream's foundation loop: it doesn't test a *definition* of
landmark yet — it tests whether the human judgment we intend to anchor every
definition against is itself stable enough to be an anchor.

What each outcome would mean:

- **Confirmed** — an external ground truth exists. Candidate definitions
  (declared, self-supervised, unsupervised) can be scored against it in later
  loops.
- **Rejected via a large "unsure" bucket** — landmark-ness may not be binary.
  That re-frames the problem (tiers? a continuum?) before any definition is
  even on the table.
- **Rejected via recalled names missing from the citer pools** — human memory
  of "the landmarks downstream of this paper" doesn't match actual citation
  links. The anchor idea itself weakens, and we'd need to understand why
  (memory wrong? citation graph incomplete? "downstream" ≠ "direct citer"?).

## Experiment — the labeling protocol

Designed to keep the labels independent of the metric under study: **no
citation counts are shown at any point**, and positives come from memory
*before* any list is displayed (so presentation order can't anchor them).

1. **Seed selection.** The researcher names 10–12 seed papers whose downstream
   literature they know cold. Their confidence is the data quality.
2. **Recall-first positives.** For each seed — before seeing any citer list —
   the researcher names the papers they'd call landmarks among its citers.
3. **Verification.** Each recalled name is checked against the seed's citer
   pool in the local S2 corpus (`D:\s2corpus`, release 2026-07-07). Hit-rate
   is part (b) of the hypothesis.
4. **Blind sample labeling.** A uniform random sample (never top-N by any
   metric) is drawn from the seed's remaining citers and presented blind —
   title, authors, year, venue, abstract; no counts. The researcher labels
   each: **landmark / not / unsure**. The unsure rate is part (a).
5. **The anchor dataset.** All labels land in a CSV beside this loop's
   notebook: seed id, citer id, label, and how the row entered (recalled vs.
   sampled) — that provenance column matters, because recalled positives and
   sampled positives were produced under different conditions.

## Results

Pending — awaiting the seed list and recall-first names (steps 1–2, which only
the researcher can produce), then the corpus verification and blind sheet
(steps 3–4).
