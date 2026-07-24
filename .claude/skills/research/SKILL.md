---
name: research
description: >
  The research process — how to frame a problem, build intuition, and
  grow understanding through open-ended workstreams of hypothesis → experiment →
  results. Research here is for knowledge - not a deliverable: nothing is
  "solved", and productionizing what you learn is a separate process. Invoke for
  any analysis, model-fitting, constant-tuning, corpus study, experiment design,
  or "derive a rule from the data" work. Read it BEFORE writing analysis code,
  choosing a method, or explaining a finding.
---

# The research process

> **A note on the name.** This skill refers to whoever's driving the research
> generically as **"the researcher."** Claude: silently read that as the actual
> person's name — infer it from `git config user.name`, the local memories, or
> the conversation — and address them by it. Do **not** edit this file to bake
> the name in: the generic wording is what's committed, personalization happens
> at read time, and that way a clone never shows a spurious diff waiting to be
> committed by accident.

This skill governs how research and analysis are done. It exists because
research done badly is worse than none: a finding the researcher can't follow is
one they can't check, and a conclusion pulled from thin air is one nobody can
trust. And it treats research as **open-ended understanding - not a deliverable**. 
There is no problem to declare *solved*, only more to learn. The process below is
built around both.

**Research is open-ended and not a march to a solution.** Frame the problem once
and build the intuition (step 1), then explore it through **workstreams** —
parallel lines of inquiry that emerge as you go. Each workstream is framed with
its own theme (step 2) and then runs a never-ending loop of **hypothesis →
experiment → results** (steps 2a–2c). You push whichever frontier you like
next - a breadth-first search across the problem space. Nothing is ever *solved*; every result
is just something newly learned and logged where it accrues. Build shared
understanding *first*, in plain language, test only a stated hypothesis, and
keep each workstream's log growing.

## The shape of the work

> **Every step is back-and-forth.** Present what you have, ask what you're unsure
> of, and wait for the researcher's response before moving to the next — the shared
> understanding is built *in* the exchange - not delivered at the end of it.

The **problem** is framed once — step 1, the umbrella. Each **workstream** that
emerges under it gets its own lighter framing — a theme, and the intuition for how
it fits the whole (step 2) — and then runs the **hypothesis → experiment →
results** loop (steps 2a–2c) open-ended. There is no step after that: no
*decision* that closes the problem, no *productionize*. Workstreams emerge freely
as you explore, and at any time you can pick a different one and push its frontier
out another hypothesis.

```
1. Frame the PROBLEM + build intuition          ← once; the umbrella
       │
       ├── 2. Frame WORKSTREAM A (theme + how it fits the problem)
       │        └─▶ 2a. hypothesis ─▶ 2b. experiment ─▶ 2c. results ─┐
       │                  ▲                                          │
       │                  └────────────── loop, open-ended ──────────┘
       ├── 2. Frame WORKSTREAM B (theme + how it fits the problem)
       │        └─▶ 2a. hypothesis ─▶ 2b. experiment ─▶ 2c. results ─┐
       │                  ▲                                          │
       │                  └────────────── loop, open-ended ──────────┘
       └── 2. Frame WORKSTREAM … (emerges as you go)

Breadth-first: pick any workstream, add its next hypothesis, expand the frontier.
Nothing is ever "solved" — each result is understanding gained, and logged.
```

### 1. Frame the problem and build the intuition

What we're actually exploring, in plain language, plus a shared mental model of
*why* — before any analysis code. Framing and intuition are one step: you can't
build intuition for a problem you haven't framed, and you haven't really framed it
until the intuition is mutual. This is where the ground-up explanation discipline
lives (see **What not to do**). You are done with this step when the researcher can
restate the problem and the rough shape of the answer in their own words — not
before.

**The step's output is a written formal problem statement**, recorded in the
problem's README before any hypothesis is proposed. Plain language still, but
precise about scope: what we are exploring, what is deliberately *out* of scope,
and what a valid answer to a question about it may look like — **including the
degenerate ones**. (A degenerate answer that reads like a footnote can reshape the
whole problem: noticing that *"the empty result is a valid answer"* may quietly
eliminate an entire family of approaches, before any data is touched.) The
statement is the umbrella every
workstream hangs off. It isn't frozen: as a workstream deepens your understanding,
you may sharpen or re-frame it — keep the old framing and *why it changed*, because
the history of how the problem itself came into focus is part of what you're
learning.

### 2. Frame the workstream and build the intuition

A workstream is one angle on the problem — a line of inquiry that emerges as you
explore, not something laid out in advance. Before its first hypothesis, give it a
lighter version of what step 1 gave the problem: a **theme or idea** naming what
this workstream is *about*, and the intuition for **how it fits into the larger
problem**. It doesn't need a formal statement the way step 1 does — but it needs
more than a label: you should be able to say, in a sentence or two, what question
this workstream is circling and why it earns a thread of its own. Record it at the
top of the workstream's README, and every hypothesis (step 2a onward) hangs off it.

### 2a. Hypothesis

Within a workstream, a single, testable claim about what's true, specific enough
that an experiment could refute it. *"A single threshold on one feature separates
most of the cases correctly"* is a hypothesis; *"let's look at the data"* is not.
Write it down, so the results in step 2c have something concrete to confirm or
reject.

**Start with the simplest hypothesis that could be true — Occam's razor.** Begin
with the fewest moving parts (one variable - not four; a straight line before a
curve) and add complexity only once a result shows it's needed. This is not
laziness, it's diagnostics: a simple hypothesis that fails tells you exactly which
assumption broke, where a complex one that fails tells you nothing, because you
can't see which part was wrong. The same goes for the experiment in step 2b — run
the smallest thing that could settle the question - not the most thorough thing you
could build.

### 2b. Experiment

Run something to test the hypothesis — a query, a fit, a simulation. Say up front
what it tests and what each possible outcome would mean. Keep it honest: carry the
worked examples through, report the whole spread rather than a flattering
headline, and reproduce any number before you lean on it. Mind the cost — live
APIs throttle, large scans are slow, and compute and data access aren't free.

### 2c. Results

What the experiment actually showed, and whether it confirms or rejects the
hypothesis. **Interpret — don't just state numbers:** say what each figure *means*
and how it connects back to the intuition from steps 1–2. A number without an
interpretation is noise. A rejected hypothesis is a real result — often the more
useful one. Whatever it shows, it's a **new learning** - not a verdict on the
problem: record it in this loop's README and add a row to the workstream's table,
so the understanding accrues where the next hypothesis will build on it.

### The loop never closes

There's no step after 2c. A result doesn't get a *solved* / *not-solved* verdict —
that isn't a question this process asks. What a result gives you is the next
question: another hypothesis to add to this workstream (back to step 2a), a new
workstream the finding suggests (a fresh step 2), or a reason to re-frame this
workstream (step 2) or even the umbrella (step 1). Pick whichever frontier you
want to push next — the work is breadth-first across the problem, and the problem
is never finished, only better understood.

**A workstream's loops don't have to build on each other.** The next hypothesis
can extend or refine the last — but it can equally be a *brand-new* claim that
just shares the workstream's theme, with nothing to do with what the previous loop
tested. A workstream isn't one deepening argument; it's a **knowledge base**, and
its README is the collected record of every hypothesis → experiment → result it
has run, independent threads included. What matters is that they're *all*
documented there, growing the workstream's understanding — not that each one
supersedes the one before.

**Productionization is deliberately out of scope.** Turning something you've
learned into shipped code — a fitted model, a rule in `src/` — is a separate
process that *uses* research output; it isn't part of research. This skill ends at
understanding.

## Standards and house patterns

Research code is still code — it holds to the repo's conventions, plus a few
specific to notebooks and plots. This section is self-contained: it doesn't assume
you've read `CLAUDE.md`, though the code rules deliberately match it.

**Reach for whatever library fits the work.** numpy, pandas, scikit-learn, torch,
and the rest are all fair game — there is no dependency-minimalism rule in research
code, unlike production code. The seaborn preference under **Plots and visuals**
(below) is specifically about *visualization*, not a limit on the analysis itself.

### Where research lives — nest by problem → workstream → loop

The research tree mirrors the shape of the work: one directory per **problem**, a
sub-directory per **workstream** inside it, and a sub-directory per **loop** (one
hypothesis→experiment→result) inside that. Every level carries its own `README.md`
(see **The READMEs are the research log**, below), and the executable detail —
Jupyter notebooks — lives at the loop level. Nothing exploratory belongs in `src/`.

```
research/
  <problem-name>/                    # one problem statement — the umbrella
    README.md                        # the formal problem statement + intuition
    <workstream-name>/               # a line of inquiry (emerges freely as you go)
      README.md                      # what it explores + a concise table of its loops
      01_<loop-name>/                # ONE hypothesis → experiment → result loop
        README.md                    # the hypothesis, the experiment, the results
        01_<loop-name>.ipynb         # the executable detail
      02_<loop-name>/
        README.md
        02_<loop-name>.ipynb
    <another-workstream>/
      ...
```

**One loop, one package.** Each loop directory holds a single
hypothesis→experiment→result and the notebook(s) that ran it — name it for the
claim it tests, and number the loops so the reading order within a workstream is
obvious. A loop is self-contained: a rerun of one doesn't drag the others.

### The READMEs are the research log — three altitudes

Documentation is the point of the whole exercise — it's where the understanding
accumulates — and it's written **as you go**, not at the end (each README *is* a
working document, updated as understanding grows). There's a README at each
level, and the right amount of detail lives at each:

- **Problem README** (`<problem>/README.md`) — the **framing**: the formal problem
  statement (scope, what's out, what a valid answer may look like, degenerate
  cases) and the plain-language intuition behind it (step 1). Keep re-framings
  here with *why* they changed. Plus a short index of the workstreams as they
  emerge.
- **Workstream README** (`<workstream>/README.md`) — the workstream's **framing**
  (step 2: its theme, and how it fits the larger problem) at the top, then a
  **concise** running table collecting its loops — the workstream's **knowledge
  base**, every hypothesis it has tried, whether or not they build on one another.
  Clear and to the point here. The detail lives one level down. For example:

  | # | Hypothesis | Experiment | What we learned |
  |---|---|---|---|
  | 1 | A single threshold on one feature separates most cases | Fit the threshold, report accuracy across the set | 62% separated against a ~70% ceiling for one-feature rules — one feature can't reach the target here |
  | 2 | … | … | … |

- **Loop README** (`<loop>/README.md`) — **one loop in full detail**: the
  hypothesis stated plainly (step 2a), the experiment written out (step 2b — what
  it runs, what each outcome would mean), and the results — interpreted, not just
  numbers (step 2c). This is where verbosity belongs. The notebook beside it holds
  the executable proof.

The thread reads top-down when you want the shape (problem → workstreams → the
table of what each taught) and bottom-up when you want the proof (a loop's README
+ its notebook).

### Notebook code quality — the same bar as the rest of the repo

A committed notebook exists so a person can read and trust it, so its code cells
hold to the repo's conventions:

- **Docstrings on every function** — Google convention (a one-line summary, then
  `Args:` / `Returns:` where a value comes back), same as the rest of the codebase.
- **Inline comments** on non-obvious steps — a cell only a machine can follow
  defeats the purpose of committing it.
- **No single-letter identifiers** — `node` not `n`, `threshold` not `t`,
  `index` not `i`. Where the project enforces this in its gate, a pre-commit hook
  that walks `.ipynb` code cells as well as `.py` files means a stray `for i in …`
  fails the check. (`_` as a pure discard is the one allowed single character.)

**Watch out for execution.** If nothing in the gate actually *runs* the notebooks,
a committed output is an unchecked claim. Until that's automated, **re-run a
notebook end-to-end before trusting or committing its outputs** — a stale committed
cell is the "relay unreproduced numbers" failure (below) in a different costume.

### Plots and visuals — clear, labeled, interpreted

A plot in a research notebook is an argument. It has to stand on its own.

- **Use declarative libraries — seaborn on top of matplotlib**, not raw matplotlib
  alone. Seaborn says *what* you want ("a scatter of x vs y colored by cohort") in
  a line where matplotlib makes you spell out *how*. The code is shorter and reads
  closer to intent. Drop to matplotlib only for finishing touches seaborn doesn't
  cover. **Still comment the plotting code** — a declarative call is terse, but it
  isn't self-documenting about *why this view*.
- **Every plot carries a title and labeled axes.** No unlabeled axis, ever. If a
  reader can't tell what they're looking at without the surrounding prose, the
  plot isn't finished.
- **Explain any scaling or transform** — a log axis, a normalization, a clipped
  range, "counts divided by the median" — on the axis label or in the cell.
  An unexplained transform is a hidden assumption.
- **Every result gets a written interpretation** — somewhere in the notebook, in
  words: what the number or plot *means* and how it connects back to the intuition
  (step 2c). A figure with no interpretation is the "uninterpreted numbers"
  failure below. State the takeaway, not just the pixels.

## ⚠️ What NOT to do — MANDATORY

These are not hypotheticals — each is a real failure mode that has cost a
researcher time. Read them as hard rules - not suggestions. Notice that most are
the same underlying mistake — running ahead of the shared understanding.

### Do not invent jargon or private metaphors

**What not to do:** coin private shorthand — *"the dial"* for some tuning
parameter, say, or *"the needle is narrower than the wobble"* written as if it
were a real description. Such a term means nothing to anyone but whoever coined it,
at the moment they coined it.

**Why it's bad:** invented shorthand reads as confusing at best and hand-wavy at
worst. It *sounds* like it's carrying meaning while actually hiding it, and it
can't be looked up or checked.

**Do instead:** say the plain, literal thing. Not "the dial" — **"one number per
case."** Not "the needle vs the wobble" — **"the target window is narrower than
the scatter in what the data requires."** If a concept genuinely needs a name,
introduce it explicitly ("call it the per-case multiplier"), define it once,
then use it consistently — that's a definition - not a metaphor.

### Do not drop theorems or machinery in cold

**What not to do:** cite something like *"max interval stabbing, which dualizes"*
as though it were shared ground — name a technique the researcher has never seen
and lean on it in the same breath.

**Why it's bad:** an argument that rests on machinery the reader doesn't have
isn't an argument to them — it's an appeal to authority. It can't be followed,
questioned, or trusted. The researcher explicitly wants to understand the
mathematics - not be handed conclusions stamped with a theorem's name.

**Do instead:** before invoking a named concept, equation, or technique, **check
the familiarity ledger** — a running record (keep one, e.g. a `concept-familiarity`
memory) of what the researcher has and hasn't heard of.

- **Listed as familiar** → use it, name it, move on. Don't re-ask.
- **Listed as unfamiliar** → do a proper ground-up background review to build the
  intuition *before* using it in an argument.
- **Not listed** → ask the researcher once whether they've seen it, act on the answer, and
  **record it in the ledger** so you never ask again.

The ledger exists precisely so this doesn't become a question every experiment —
keep it current. Either way, introduce a concept before you rely on it: name it,
explain in plain terms what it is and *why it applies here*, ideally with a tiny
concrete example.

### Do not explain top-down — start from the ground

**What not to do:** lead with the formal reduction and the conclusion, then
backfill — explaining at the altitude of the answer instead of building up to it.

**Why it's bad:** it inverts how understanding forms. The reader has to hold a
formalism they don't yet see the point of, hoping it'll pay off. Comprehension
comes from assembling the pieces - not from being shown the finished assembly and
told where each piece went.

**Do instead:** explain it **as if to a five-year-old, first.** Start from something
obviously true and small. Add one idea at a time, each building on the last,
checking the ground is solid before the next step. The formal statement is where
you *arrive* - not where you begin.

### Do not jump to experiments before the reasoning is shared

**What not to do:** start running scripts — searches, fits, reproductions — while
the *why* is still only in your head, producing numbers before you and the
researcher have agreed on what question they answer.

**Why it's bad:** an experiment is only meaningful against a hypothesis. Run it
first and the output is just numbers with no frame. The reader can't tell a
confirmation from a coincidence, and you've spent effort — often live API budget
or compute — buying a result nobody's ready to interpret. This is what the framing
and hypothesis steps (1, 2, and 2a) are for.

**Do instead:** follow the loop. Reach agreement on the intuition (steps 1–2) and
a stated hypothesis (step 2a) *before* writing analysis code. When you do run
something, say up front what it's testing and what each outcome would mean.

### Do not relay numbers you haven't reproduced — or leave them uninterpreted

**What not to do:** quote a figure — a headline ceiling, a ratio — from a
notebook's prose as established fact before reproducing any of it. (Reproducing it
later doesn't rescue the claim already made. The mistake is asserting it *before*
the check.)

**Why it's bad:** committed prose — even your own from an earlier session — is a
*claim*, not a verified result. Relaying it as fact launders an unchecked number
into a decision. A researcher can end up choosing a direction off figures no one
has confirmed.

**Do instead:** before a number drives a decision, reproduce it from the data
yourself, or label it plainly as unverified ("the notebook *claims* X — unverified
here"). And when you report a number, **interpret it** — say what it means and how
it connects to the intuition from steps 1–2, don't just state the figure.
Reproducing a number independently is the standard for *verification*; saying what
it means for the question is the standard for *reporting*. Both are required.
