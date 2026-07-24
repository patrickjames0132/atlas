# Landmark selection — which citers belong on the map

The research log for the question *"given a seed paper and the papers citing it,
which ones does the map show?"* — framed fresh on 2026-07-23 under the
[`research` skill](../../.claude/skills/research/SKILL.md). Written as we go: the
cycle's steps 1–5 live here, the executable detail lives in the notebooks
alongside.

**Deliberate fresh start.** An earlier attempt at a related question ran on the
retired `citation-threshold` branch and was abandoned. Patrick's instruction
(2026-07-23) was to start over with fresh eyes and inherit **nothing** from it —
no prior formulation, no prior findings, no prior constants. That branch's
collected corpus sample may be borrowed later as *data* if it fits the
experiments we design here, and even then the dataset may be redefined. Nothing
in this log is carried over from it.

## Step 1 — Framing and intuition ✅ settled 2026-07-23

### The problem in plain language

Atlas draws a seed paper in the middle of a map and surrounds it with its
neighbours: papers the seed cites, papers that cite it, a recent slice of those,
and similar papers.

The citing side is where the difficulty lives. A well-known paper is cited by
thousands to tens of thousands of papers; a graph stays readable at tens of nodes,
maybe low hundreds. Something has to choose which citers a person sees, and that
choice **is the product** — whatever rule picks those papers is what the user
learns about the field. Layout and the AI teacher are both downstream of it.

### Why a single citation cutoff cannot work

The cheapest signal about a citing paper is how many times it has itself been
cited: free, present in every provider, and a plausible stand-in for "did this
matter". But a raw count only means something *relative to something else*, and it
fails on three axes:

1. **Against time.** A 2024 paper with 80 citations may be a bigger deal than a
   1990 paper with 300 — the 1990 paper had thirty-four extra years to collect
   them.
2. **Against the seed.** The papers citing a famous seed are themselves famous;
   the papers citing a solid niche paper are not. One cutoff floods the first map
   and empties the second.
3. **Against the field.** Machine learning cites far more, and faster, than pure
   mathematics. A count that is remarkable in one is ordinary in the other.

So any workable rule compares a citer's count against some *expectation*, and the
research question is what that expectation is built from.

### What the map is for (Patrick, 2026-07-23)

- **The map should show how the field developed over time** — not simply the
  biggest hitters wherever they happen to land.
- **The count of landmarks is not a target.** What matters is identifying genuine
  landmarks that evolved ideas in the field. They need not be the most
  ground-breaking papers in existence, but they should sit in the upper echelon of
  citation counts.
- **Zero landmarks is a valid answer.** Especially for brand-new seeds. We do not
  force a landmark onto the screen when no paper has yet earned the label.

### The definition these converge on

"Show the giants" and "show how the field developed over time" look like they
fight — the giants clump into whatever years the field was hot. They stop fighting
once the bar is measured **against a paper's contemporaries**:

> **A citer is a landmark when its citation count is far above what a paper of its
> age would normally reach.**

Agreed by Patrick, 2026-07-23. This gets both goals at once: the bar stays high,
so we get genuine standouts rather than padding; and spread across time arrives as
a *consequence* rather than an imposed quota, because every era can produce
landmarks if it had standouts.

### The structural consequence: no pool-relative rules

The "zero is okay" requirement rules out an entire family of rules on its own —
every rule that ranks a seed's citers and takes a slice off the top (top-N, top
5%, any quantile of the pool) **always returns something**. Handed a 2025 paper
cited eleven times, a quantile rule dutifully returns its "best" citers as
landmarks, which is exactly the false claim we don't want.

For zero to be reachable, the bar must be defined **without reference to the
pool's own ranking** — an absolute expectation a paper either clears or does not.
This conclusion came out of framing, before any data.

### How we will grade a rule

There is no public ground truth for "which papers make the best map of a field",
so grading had to be designed rather than assumed. Three mechanisms, deliberately
**not** of equal standing:

| Mechanism | What it is | What it actually measures |
|---|---|---|
| **Patrick's labels** (primary) | 10 hand-picked seeds, citers marked landmark / not / unsure | **Correctness.** The only direct encoding of the goal; every other signal is a proxy for this judgment. |
| **A second annotator** (Claude labels the same seeds) | Not self-supervision — a second opinion on identical input | **Consistency.** Whether "landmark" is a stable judgment at all. Sharp disagreement would mean no rule can be graded against either annotator — worth knowing before any fitting. |
| **Self-supervised labels** | Labels derived from network structure, e.g. a citer is a landmark if the seed's *other* citers heavily cite it | Whether the descendants' own voting agrees with human judgment. Label-free, so it scales — *if* it agrees. |
| **Clustering / silhouette** | Unsupervised separation in feature space | **Separation, not correctness.** Answers "is there a natural gap here, or is landmark a line drawn through a smooth continuum?" A rule can separate data cleanly on something irrelevant. |

Only the first grades us. The rest are interesting results in their own right
(Patrick, 2026-07-23) and are scheduled as their own hypotheses below.

## Step 2 — Hypotheses

Following the skill's Occam's razor rule: start with the fewest moving parts and
add complexity only when a result demands it. **Age only to begin with**; field
enters only if the labels show age is insufficient (Patrick, 2026-07-23).

| # | Hypothesis | Experiment | Result | Decision |
|---|---|---|---|---|
| 1 | *(proposed)* A citer's citation count relative to **an age-based expectation alone** separates Patrick's landmark labels from his non-landmark labels. | Fit the expectation curve from citation count vs. age; score labelled citers against it; measure separation. | — | — |
| 2 | *(planned)* Landmark vs non-landmark is a **natural grouping**, not a line through a continuum. | Cluster labelled citers in the age/count feature space; silhouette score. | — | — |
| 3 | *(planned)* **Self-supervised labels** (citers heavily cited by the seed's other citers) agree with Patrick's labels. | Compute intra-pool citation counts; compare against the hand labels. | — | — |
| 4 | *(planned)* Claude's independent labels agree with Patrick's. | Label the same seeds blind; measure agreement. | — | — |

## Step 3–5 — Experiments, results, decisions

Nothing run yet. Awaiting the 10 labelled seeds.

## Status

- ✅ **Step 1 framing** — settled 2026-07-23.
- ⏳ **Blocked on data** — Patrick is picking 10 seeds (a deliberate spread: an old
  classic, a mid-career paper, something recent enough that it *should* return
  zero landmarks).
- ⏳ **Tooling** — the `research` dependency group (pandas, seaborn, jupyter) went
  out with the 2026-07-22 research reset and must be added back before any
  notebook runs.
