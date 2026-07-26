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

   **Label semantics** (pinned 2026-07-25, when the first sheet turned out to
   be almost entirely unrecognized papers — exactly what a uniform draw from
   a citer pool *should* produce):

   - `landmark` — actual recognition of the paper as one that matters.
   - `not` — "I don't recognize this, **and** it's from a field where I would
     recognize a landmark." Within the researcher's own field, non-recognition
     is the instrument working: a paper nobody who knows the field has heard
     of is, under this problem's framing of landmark, not one. This is a
     reading, not a guess.
   - `unsure` — "I can't judge this": chiefly papers outside the researcher's
     competence (e.g. physics citers of Hawking), where non-recognition
     carries no information; also genuine torn cases.

   **Guessing from title plausibility is prohibited** — it would measure how
   grand a title sounds, not influence, and launder that heuristic in as
   ground truth. A sheet that comes back overwhelmingly `not` is itself a
   quantitative result: the base rate of landmarks in a uniform citer draw.
5. **The anchor dataset.** All labels land in a CSV beside this loop's
   notebook: seed id, citer id, label, and how the row entered (recalled vs.
   sampled) — that provenance column matters, because recalled positives and
   sampled positives were produced under different conditions.

## Known limitations of the anchor — declared before labeling began

Stated by the researcher up front (2026-07-25), before any labels existed:

- **Recall is sparse.** The researcher hasn't been reading papers closely for
  a while; recalled positives per seed will be few, possibly zero for some
  seeds. Consequences: the recall hit-rate (hypothesis part b) will be a
  coarse estimate, and the blind-sampled labels (step 4) carry more of the
  anchor's weight than originally sketched. Sparse-but-honest beats padded —
  a seed with zero recalled landmarks stays in, recorded as exactly that.
- **The anchor is AI/ML-biased.** Seeds and judgments come from the fields the
  researcher actually knows; physics, math, and the rest of arXiv are
  unrepresented *by construction*. Anything a later loop validates against
  this anchor is validated **for AI/ML only** — cross-field generalization is
  an assumption the anchor cannot test (recorded as A4 in the problem README).
- **The seeds skew famous.** Memorable seeds are, almost by definition,
  majorly-cited ones — so the anchor over-represents huge citer pools and
  under-represents obscure seeds (noted by the researcher mid-collection,
  2026-07-25). Only Correlated Q-Learning and QMIX sit below the blockbuster
  tier, so they carry outsized weight for any later question about whether a
  definition transfers to quiet seeds — and conclusions about the obscure-seed
  regime mostly can't come from this anchor at all.

## Results

### Part (b) — recall verification: 6 of 9 recalled citers are real citers

Run 2026-07-25 against corpus release 2026-07-07 (the notebook beside this
README is the executable proof). Verified in-pool: LoRA and BERT citing
*Attention Is All You Need*; DDPG, Double DQN, and Rainbow citing *Playing
Atari*; ResNet citing AlexNet.

The three misses share one shape — **human recall tracks influence lineage,
not reference lists**:

- **Sparsely-Gated MoE ← AIAYN** — impossible as a citer: the corpus dates MoE
  2017-01-23 and AIAYN 2017-06-12, so MoE sits in the Transformer's *ancestry*.
  Recall reversed the direction of influence.
- **AIAYN ← AlexNet** — no citation edge in the corpus. An association by
  shared fame and era; the Transformer's lineage runs through NLP, not through
  AlexNet's reference list.
- **PPO ← Playing Atari** — no edge, and direction can't explain it (PPO is
  2017-07-20, four years later). Either PPO genuinely doesn't cite the 2013
  workshop paper (plausibly citing later DQN-era work instead), the corpus is
  missing the edge, or memory again linked lineage rather than citation. Open
  sub-question.

**What this means for the anchor:** recall positives are unusable unverified —
a third of them were false *as citations* while arguably true *as influence*.
The verification step is load-bearing, not paranoia. The six verified
positives enter the anchor; the three misses are excluded from it but kept
here as data about how recall behaves — and as an early hint that "matters in
its own right" (influence) and "cites the seed" are related but **not
identical** notions, which the problem framing may eventually have to care
about.

**Also observed:** distinct-citer pool sizes span 476 (Correlated Q-Learning)
to 180,306 (AIAYN) — a ~380× spread across just ten seeds. First concrete
sight of the famous-seed skew declared above, and a preview of assumption A3's
"different citation worlds."

### Part (a) — labeling was decisive; the instrument's calibration is now the question

The researcher reviewed all 150 sampled rows (2026-07-25) and recognized none.
Per the pinned semantics that gave: **135 within-field `not`, 15 out-of-field
`unsure`** (Hawking's citers), zero within-field hesitation — nominally
confirming "crisp enough to label decisively" — and **zero landmarks in the
uniform draw**.

**The base rate this measures:** 0 recognized landmarks in 135 uniform
within-field draws. If landmarks made up even 2% of a citer pool, a zero-hit
draw of 135 would happen only ~6.5% of the time (0.98¹³⁵ ≈ 0.065) — so on this
evidence, recognizable landmarks are at most a couple percent of a pool and
plausibly well under 1%. The tail any single-citer rule hunts is needle-thin,
and the anchor's positives-per-pool confirm it: 6 verified landmarks against
pools of 13k–180k citers.

**Declared immediately after labeling — a caveat that softens the negatives:**
the researcher flagged that their AI/ML grounding is coursework-deep, not
research-deep (a taught master's, no thesis, limited time in the literature),
so the recognition instrument behind the `not` labels may be weaker than the
pinned semantics assumed. Honest reading: `not` here means *"not recognized by
a textbook-trained practitioner"* — evidence of obscurity, but not proof of
non-landmark-ness. The anchor's negatives carry this caveat until checked.

**The proposed check — additional raters:** the researcher suggested having
coworkers who are deeper in the field label the same sheet, blind, under the
same rules. That would (1) hunt for landmarks the first pass missed and
(2) measure inter-rater agreement, turning instrument calibration from a worry
into a number. Natural candidate for this workstream's next loop.

### Verdict

- **Part (a)** — labeling was decisive (zero within-field unsures), but the
  loop surfaced that decisiveness and *calibration* are different things, and
  calibration is now the open question.
- **Part (b)** — partially rejected: a third of recalled positives weren't
  citers (lineage-not-citation conflations).
- **The anchor exists** (`anchor.csv`: 6 `landmark` / 135 `not` / 15 `unsure`,
  with provenance) and is usable under its declared limits; the negatives are
  provisional pending a rater check.
