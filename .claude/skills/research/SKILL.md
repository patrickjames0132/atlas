---
name: research
description: >
  The research process for Atlas — how to frame a problem, build intuition, form
  and test hypotheses, and derive rules/constants worth productionizing. Invoke for
  any analysis, model-fitting, constant-tuning, corpus study, experiment design, or
  "derive a rule from the data" work. Read it BEFORE writing analysis code, choosing
  a method, or explaining a finding.
---

# The research process

> **A note on the name.** This skill refers to whoever's driving the research
> generically as **"the researcher."** Claude: silently read that as the actual
> person's name — infer it from `git config user.name`, the local memories, or
> the conversation — and address them by it. Do **not** edit this file to bake
> the name in: the generic wording is what's committed, personalization happens
> at read time, and that way a clone never shows a spurious diff waiting to be
> committed by accident.

This skill governs how research and analysis are done in Atlas. It exists because
research done badly is worse than none: a finding the researcher can't follow is
one they can't check, and a conclusion pulled from thin air is one nobody can trust. The
process below is built to prevent that.

> **The cycle runs in a fixed order:** frame + build intuition → hypothesis →
> experiment → results → decision → (productionize, or loop back). Build shared
> understanding *first*, in plain language; only once the idea is mutual do we
> test it; only once a result is in do we decide; only once we've decided it's
> solved do we build anything durable. Don't skip stages, and don't run ahead of
> the shared understanding — most of the ways research goes wrong are really that
> one thing.

## The research cycle

> **Every step is back-and-forth.** Present what you have, ask what you're unsure
> of, and wait for the researcher's response before moving to the next — the shared
> understanding is built *in* the exchange, not delivered at the end of it.

Six steps. Steps 1–5 are a loop; step 6 is the exit taken only once the problem
is genuinely solved. Most work goes around 1–5 more than once before it earns
step 6.

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                   │
  ▼                                                                   │
1. frame + intuition ─→ 2. hypothesis ─→ 3. experiment ─→ 4. results ─→ 5. decision
  ▲                        ▲                                              │
  │                        │                                             solved
  └── reframe ─────────────┴──── more evidence                            │
                                                                          ▼
                                                              6. productionize
```

### 1. Frame the problem and build the intuition

What we're actually solving, in plain language, plus a shared mental model of
*why* — before any analysis code. Framing and intuition are one step: you can't
build intuition for a problem you haven't framed, and you haven't really framed it
until the intuition is mutual. This is where the ground-up explanation discipline
lives (see **What not to do**). You are done with this step when the researcher can
restate the problem and the rough shape of the answer in their own words — not
before.

**The step's output is a written formal problem statement**, recorded in the
research log before any hypothesis is proposed. Plain language still, but precise
about scope: what we are trying to solve, what counts as a solution, what is
deliberately *out* of scope, and what a valid answer may look like — **including
the degenerate ones**. (On landmark selection, "zero landmarks is a valid answer"
looked like a minor clarification and turned out to eliminate an entire family of
rules, before any data was touched.) Write it down because it is what **step 5
measures against**: *solved* means this statement is satisfied. When it isn't, the
statement is also what tells you which way to loop — a hypothesis that failed on
its own terms sends you back to step 2, while a statement that no longer describes
the real problem sends you back here.

### 2. Hypothesis

A single, testable claim about what's true, specific enough that an experiment
could refute it. *"A per-citer citation threshold can hold most seeds inside a
20–40 landmark band"* is a hypothesis; *"let's look at the data"* is not. Write it
down, so the results in step 4 have something concrete to confirm or reject.

**Start with the simplest hypothesis that could be true — Occam's razor.** Begin
with the fewest moving parts (one variable, not four; a straight line before a
curve) and add complexity only once a result shows it's needed. This is not
laziness, it's diagnostics: a simple hypothesis that fails tells you exactly which
assumption broke, where a complex one that fails tells you nothing, because you
can't see which part was wrong. The same goes for the experiment in step 3 — run
the smallest thing that could settle the question, not the most thorough thing you
could build.

### 3. Experiment

Run something to test the hypothesis — a query, a fit, a simulation. Say up front
what it tests and what each possible outcome would mean. Keep it honest: carry the
worked examples through, report the whole spread rather than a flattering
headline, and reproduce any number before you lean on it. Mind the cost — live
APIs throttle and the corpus lives on one machine (see **Standards**).

### 4. Results

What the experiment actually showed, and whether it confirms or rejects the
hypothesis. **Interpret — don't just state numbers:** say what each figure *means*
and how it connects back to the intuition from step 1. A number without an
interpretation is noise. A rejected hypothesis is a real result — often the more
useful one — so record what it taught us either way.

### 5. Decision

Given the results, is the problem solved?

- **Solved** → go to step 6.
- **Needs reframing** — the results say we were asking the wrong question → loop
  back to **step 1**.
- **Needs more evidence** — the framing holds but this hypothesis was wrong or
  incomplete → loop back to **step 2**.

This is a genuine fork and usually the researcher's call. Surface it explicitly; don't
slide past it into more code.

### 6. Productionize

Reached only when step 5 says *solved*. Turn the finding into durable code: a
fitted model published through `ml_pipelines/` (with its research write-up under
`research/`), or a direct change to `src/` when the result is a rule or constant
rather than a model. This is the only stage that writes lasting artifacts —
everything before it is exploration. (See **Standards** for the
data-driven-over-magic-numbers pattern and the notebook-gating rule.)

## Standards and house patterns

Research code is still Atlas code — it holds to the repo's conventions, plus a few
specific to notebooks and plots. This section is self-contained: it doesn't assume
you've read `CLAUDE.md`, though the code rules deliberately match it. (The
standards for **productionizing** a solved finding into `ml_pipelines/` are a
later addition — for now this covers the research log and its notebooks.)

**Reach for whatever library fits the work.** numpy, pandas, scikit-learn, torch,
and the rest are all fair game — there is no dependency-minimalism rule in research
code, unlike the shipped app. The seaborn preference in §4 is specifically about
*visualization*, not a limit on the analysis itself.

### 1. Where research lives — a package per problem

Every problem we frame gets its **own sub-directory under `research/`**, following
the same package pattern as the rest of the repo: one directory, one concern, its
own `README.md`. Experiments and their results live as **Jupyter notebooks** in
that directory — that's where analysis code actually runs; nothing exploratory
belongs in `src/`.

**Split notebooks logically** — don't force everything into one `analyze.ipynb`.
Often the clean cut is **one notebook per hypothesis/experiment**, so each reads
as a self-contained argument and a rerun of one doesn't drag the others. Name them
so the reading order is obvious.

```
research/
  <problem-name>/
    README.md              # the research log — see below
    01_<hypothesis>.ipynb  # one experiment + its results
    02_<hypothesis>.ipynb  # the next, split where it reads more cleanly apart
```

When a finding is decided-solved and earns durable code, *that* lands in
`ml_pipelines/` or `src/` (cycle step 6), kept separate from the research log.

### 2. The README is the research log

The sub-directory's `README.md` documents the **entire research cycle except
productionization**, at a high level (the notebook holds the executable detail).
It's the one document someone can read to understand what we did and why. It
tracks, and is written **as we go**, not at the end (it *is* the working document,
the way `OnePager.md` is for features):

- **Problem framing & intuition** (step 1) — the **formal problem statement**
  (see step 1: scope, what counts as a solution, what a valid answer may look
  like), plus the mental model that led to it in plain
  language. **Including re-framings:** when a decision sends
  us back to step 1, the README keeps the old framing and *why it changed*, not
  just the latest one. The history is the point.
- **Hypotheses, experiments, results** (steps 2–4) — ideally a running table, so
  the thread from claim → test → outcome is legible at a glance. For example:

  | # | Hypothesis | Experiment | Result | Decision |
  |---|---|---|---|---|
  | 1 | A per-citer threshold holds most seeds in 20–40 | Fit `(a, p, β, FLOOR)`, report the spread | 31.6% in band vs a ~35% family ceiling | Reframe — band unreachable |
  | 2 | … | … | … | … |

- **Decisions** (step 5) — what each result concluded and where it sent us
  (solved / reframe / more evidence).

### 3. Notebook code quality — the same bar as the rest of the repo

A committed notebook exists so a person can read and trust it, so its code cells
hold to the repo's conventions:

- **Docstrings on every function** — Google convention (a one-line summary, then
  `Args:` / `Returns:` where a value comes back), same as `src/`.
- **Inline comments** on non-obvious steps — a cell only a machine can follow
  defeats the purpose of committing it.
- **No single-letter identifiers** — `node` not `n`, `threshold` not `t`,
  `index` not `i`. This is **machine-enforced**: the pre-commit hook
  (`bin/check_identifiers.py`) walks `.ipynb` code cells as well as `.py` files,
  so a stray `for i in …` fails the gate. (`_` as a pure discard is the one
  allowed single character.)

**Not yet enforced — execution.** Nothing in the gate currently *runs* the
notebooks, so a committed output is an unchecked claim (this is the open "Gate
research notebooks" ticket in `OnePager.md`). Until it lands, **re-run a notebook
end-to-end before trusting or committing its outputs** — a stale committed cell is
the "relay unreproduced numbers" failure (below) in a different costume.

### 4. Plots and visuals — clear, labeled, interpreted

A plot in a research notebook is an argument; it has to stand on its own.

- **Use declarative libraries — seaborn on top of matplotlib**, not raw matplotlib
  alone. Seaborn says *what* you want ("a scatter of x vs y colored by cohort") in
  a line where matplotlib makes you spell out *how*; the code is shorter and reads
  closer to intent. Drop to matplotlib only for finishing touches seaborn doesn't
  cover. **Still comment the plotting code** — a declarative call is terse, but it
  isn't self-documenting about *why this view*.
- **Every plot carries a title and labeled axes.** No unlabeled axis, ever. If a
  reader can't tell what they're looking at without the surrounding prose, the
  plot isn't finished.
- **Explain any scaling or transform** — a log axis, a normalization, a clipped
  range, "counts divided by the median seed" — on the axis label or in the cell.
  An unexplained transform is a hidden assumption.
- **Every result gets a written interpretation** — somewhere in the notebook, in
  words: what the number or plot *means* and how it connects back to the intuition
  (step 4). A figure with no interpretation is the "uninterpreted numbers" failure
  below. State the takeaway, not just the pixels.

## ⚠️ What NOT to do — MANDATORY

These are not hypotheticals. Every one happened in the session that created this
skill (2026-07-22, the citation-threshold analysis), and each lost the researcher
or wasted their time. Read them as hard rules, not suggestions. Notice that most are
the same underlying mistake — running ahead of the shared understanding.

### 1. Do not invent jargon or private metaphors

**What I did:** coined *"the dial"* for a per-seed multiplier, and wrote *"the
needle is narrower than the wobble"* as if it were a real description. Neither
term means anything to anyone but me at the moment I made it up.

**Why it's bad:** invented shorthand reads as confusing at best and hand-wavy at
worst. It *sounds* like it's carrying meaning while actually hiding it, and it
can't be looked up or checked.

**Do instead:** say the plain, literal thing. Not "the dial" — **"one number per
seed."** Not "the needle vs the wobble" — **"the target window is narrower than
the scatter in what the data requires."** If a concept genuinely needs a name,
introduce it explicitly ("call this `m`, the seed's multiplier"), define it once,
then use it consistently — that's a definition, not a metaphor.

### 2. Do not drop theorems or machinery in cold

**What I did:** cited *"max interval stabbing, which dualizes"* and the
interval-stabbing argument as though they were shared ground — named a technique
the researcher had never seen and leaned on it in the same breath.

**Why it's bad:** an argument that rests on machinery the reader doesn't have
isn't an argument to them — it's an appeal to authority. It can't be followed,
questioned, or trusted. The researcher explicitly wants to understand the
mathematics, not be handed conclusions stamped with a theorem's name.

**Do instead:** before invoking a named concept, equation, or technique, **check
the familiarity ledger** — the `concept-familiarity` memory, a running
record of what the researcher has and hasn't heard of.

- **Listed as familiar** → use it, name it, move on. Don't re-ask.
- **Listed as unfamiliar** → do a proper ground-up background review to build the
  intuition *before* using it in an argument.
- **Not listed** → ask the researcher once whether they've seen it, act on the answer, and
  **record it in the ledger** so you never ask again.

The ledger exists precisely so this doesn't become a question every experiment —
keep it current. Either way, introduce a concept before you rely on it: name it,
explain in plain terms what it is and *why it applies here*, ideally with a tiny
concrete example.

### 3. Do not explain top-down — start from the ground

**What I did:** led with the formal reduction and the conclusion, then backfilled.
Explained at the altitude of the answer instead of building up to it.

**Why it's bad:** it inverts how understanding forms. The reader has to hold a
formalism they don't yet see the point of, hoping it'll pay off. Comprehension
comes from assembling the pieces, not from being shown the finished assembly and
told where each piece went.

**Do instead:** explain it **as if to a five-year-old, first.** Start from something
obviously true and small. Add one idea at a time, each building on the last,
checking the ground is solid before the next step. The formal statement is where
you *arrive*, not where you begin. (This is the standing feedback saved as the
`research-explain-from-the-ground-up` memory — this skill is where it's operational.)

### 4. Do not jump to experiments before the reasoning is shared

**What I did:** started running scripts — random-restart searches, ceiling
reproductions — while the *why* was still only in my head. Produced numbers before
the researcher and I agreed on what question they answered.

**Why it's bad:** an experiment is only meaningful against a hypothesis. Run it
first and the output is just numbers with no frame; the reader can't tell a
confirmation from a coincidence, and I've spent effort (and often live API budget
or compute) buying a result nobody's ready to interpret. This is steps 1–2 of the
cycle existing for a reason.

**Do instead:** follow the cycle. Reach agreement on the intuition (step 1) and a
stated hypothesis (step 2) *before* writing analysis code. When you do run
something, say up front what it's testing and what each outcome would mean.

### 5. Do not relay numbers you haven't reproduced — or leave them uninterpreted

**What I did:** quoted *"~35% ceiling"* and *"1.9× vs 1.65×"* from a notebook's
prose as established fact, before I'd reproduced any of it. (Later I did reproduce
the ceiling from scratch, which is the one thing that went right; the mistake was
asserting it *before* that.)

**Why it's bad:** committed prose — even my own from an earlier session — is a
*claim*, not a verified result. Relaying it as fact launders an unchecked number
into a decision input. The researcher was about to pick a target band off figures I
hadn't confirmed.

**Do instead:** before a number drives a decision, reproduce it from the data
yourself, or label it plainly as unverified ("the notebook *claims* X; I haven't
checked it"). And when you report a number, **interpret it** — say what it means
and how it connects to the intuition from step 1, don't just state the figure.
Reproducing the ceiling independently is the standard for *verification*; "here is
what that 35% actually tells us about the rule" is the standard for *reporting*.
Both are required.
