# Citation coverage: preprints, completeness, and S2 vs OpenAlex

Why the graph talks to **two** academic-data sources (Semantic Scholar +
OpenAlex), what "citation completeness" actually means, and how the two
sources compare — with real measured numbers. Written to settle a recurring
question: *could we drop S2 and go OpenAlex-only?* Read this before touching
`services/graph/build.py`'s dual-source citation logic or the `integrations/`
clients.

**TL;DR.** OpenAlex is competitive-to-better than S2 for **journal-native
fields (e.g. physics)**, but **materially worse for the arXiv-native ML/AI
ecosystem** — not just in raw citation *counts* (~3–4× undercount) but in
*which* top-cited citers it surfaces (~20–40% overlap with S2's landmarks).
The gap is a citation-*extraction* problem, so it can't be fixed by smarter
resolution or a preprint-dedup heuristic. Going OA-only is viable if the app
is about graph *structure*; it's a visible regression wherever ML citation
*magnitude and landmark ranking* drive the UX.

## The concepts

### Preprint

A **preprint** is a paper made public *before* (or without) formal peer
review. **arXiv is a preprint server** — every arXiv paper is a preprint.
Many preprints are later published in a peer-reviewed venue (journal or
conference) as the **version of record** (VoR), often with a *different
title*, revised content, and a **DOI**. So the same intellectual work
routinely exists as **two records**:

- the **arXiv preprint** (id like `1512.03385`), and
- the **published version** (a DOI, e.g. in CVPR / Nature / PRL).

This one-work-two-records fact is the root of almost every citation-count
discrepancy below.

### arXiv DOI

A **DOI** is a permanent document id (`10.<registrant>/<suffix>`). Since 2022
arXiv auto-mints one for every preprint: `10.48550/arXiv.<id>` (ResNet's is
`10.48550/arXiv.1512.03385`). That DOI points at the **arXiv preprint
record** — a *different* DOI from the published version's. Our
`openalex.resolve_work` tries `doi:10.48550/arXiv.{id}` first, so by
construction it fetches the **preprint** OA work.

### References vs. citations — the direction matters

- **References** = the papers a seed *cites* (outbound; its own bibliography).
  Parsed from the seed's own reference list, so reliable in principle.
- **Citations** = the papers that *cite the seed* (inbound; "who pointed at
  this"). The hard one: it needs the database to have indexed **every** citing
  paper and correctly parsed *their* reference lists.

**"Citation completeness" is almost entirely about the inbound count.**

### Why preprints break citation aggregation

If a paper exists as both an arXiv preprint and a published article, some
later papers cite the arXiv id and others cite the published DOI. A database
only aggregates those into **one** number if it **merges** the two records.
If it doesn't, citations **split** across two works and each looks
under-cited — the **duplicate-works problem**. OpenAlex is more prone to it
than S2, and (see below) provides no link from the preprint record to its VoR.

## Findings (measured against the live APIs, 2026-07-12)

All numbers below come from the companion notebook,
[`research/citation_coverage/analyze.ipynb`](../research/citation_coverage/analyze.ipynb)
(its [README](../research/citation_coverage/README.md) covers the caveats and
how to re-run). Counts drift over time; the *patterns* are the point.

### 1. Coverage: OA undercounts ML, not physics

23 arXiv seeds (18 ML, 5 physics) — S2's `citationCount` vs OpenAlex's
`cited_by_count`. `OA best` = the highest count among OA's preprint record and
its most-cited same-title record.

| Field | n | median OA_best / S2 | # undercounting by >2× |
|---|--:|--:|--:|
| **ML** | 17 | **0.23** | **10 / 17** |
| **Physics** | 5 | **1.19** | 0 / 5 |

The ML aggregate carries *resolution noise* (generic titles like "BERT" /
"Attention is all you need" mis-match in a title search). The **clean signal**
is OA's *own arXiv-DOI record* (guaranteed the same paper — zero resolution
ambiguity) vs S2:

- GPT-3 **0.05**, CLIP **0.10**, Llama 2 **0.15**, QMIX **0.17**,
  EfficientNet **0.20**, GCN **0.22**, ViT **0.33**, Adam 0.50, word2vec 0.52,
  BatchNorm 0.52, Distillation 0.56, VGG 0.67 — **median ≈ 0.28**.
- Physics: all ≥ 0.73, usually **> 1** (OA has *more* than S2).

So OA knows roughly a quarter-to-a-third of the citers S2 does for
arXiv-native ML papers, and is fine-to-better for physics.

### 2. Resolution: arXiv-DOI lands on the preprint stub, with no way back

The app's cheapest-first `resolve_work` fetches the arXiv-DOI record, which is
the **preprint**. For papers with a real VoR that's catastrophic:

| Seed | S2 | OA via arXiv-DOI (preprint) | OA via title (canonical) |
|---|--:|--:|--:|
| ResNet | 233,242 | 4,734 | **222,747** |
| LIGO GW150914 | 3,560 | 8 | **14,324** |
| Maldacena | 19,917 | 17 | **14,567** |

The hybrid currently **masks** this: `build.py` takes `max(S2, OA)`, so the
graph shows S2's correct 233k. **Drop S2 without fixing resolution and
ResNet's node reads 4,734 citations, LIGO's reads 8.**

Can OA fix this itself? **No clean primitive.** A preprint work carries no
`versions` link and empty `related_works` — its `locations` list the arXiv/
Zenodo mirrors but never the published article, which is a *separate* work
with no back-reference. A `type:article` filter helps for physics (a real VoR
exists) but *hurts* arXiv-only ML (forces a match onto some other, lower-cited
article). So OA-only would still need a **title/year canonical-picking
heuristic** — less than cross-source dedup, but not free, and imperfect for
short/generic ML titles.

### 3. Root cause: ML is preprint-native, and OA under-extracts preprint citations

It isn't a "missing physics corpus" — OA is *great* for physics. The split is
about **where citations live**:

- **ML/AI is preprint-native** — papers cite each other as **arXiv preprints**
  in the bibliography. OA historically under-extracts arXiv-preprint→preprint
  citations, so that dense ML citation web is largely invisible to it. (GPT-3's
  preprint even has a NeurIPS location attached, yet only 3,029 citers
  aggregate to it vs S2's 60,521.)
- **Physics is journal-native** — cites resolve to journal DOIs OA indexes
  thoroughly. Hence physics ≥ S2.
- **S2 was built on exactly this arXiv/CS preprint graph**, so it captures what
  OA misses.

### 4. Quality over quantity? OA's *top* citers differ too

The app never shows all citers — `build.py` keeps the top `cite_limit` by
impact. So the sharper question is whether OA surfaces the **same landmark
citers**, not the same total. Overlap of the top-15 most-cited citers,
S2 vs OA, on three papers small enough to pull S2's full citer list (so its
true top-cited are present):

| Seed | top-15 citer overlap |
|---|--:|
| QMIX | **3 / 15** |
| MADDPG | **3 / 15** |
| Rainbow | **6 / 15** |

Qualitatively (QMIX): S2's top citers are the MARL landmarks — *StarCraft
Multi-Agent Challenge, QTRAN, Value-Decomposition Networks, MAVEN, QPLEX*.
OA's top citers are mostly **applied/journal papers** — *Distributed Learning
in Wireless Networks, Pervasive AI for IoT, Adaptive Traffic Signal Control,
Renewable-energy microgrids*. OA also **duplicates** records (MuZero appears
twice in Rainbow's OA citers) and undercounts the landmarks' own counts, so
its *ranking* is skewed, not just its totals. **So for ML it's not a missing
junk tail — the top of the list is a different, lower-quality set.** This gap
is extraction-driven, so a preprint-dedup heuristic would **not** recover it.

## How the hybrid divides labor (and why OpenAlex owns citations)

`services/graph/build.py` splits the graph across the two sources:

| Relation | Source | Whose citation counts |
|---|---|---|
| Seed | S2 (`get_paper`) | S2 |
| References (papers the seed cites) | S2 (`s2.references`) | S2 |
| Similar (purple) | S2 (`recommendations`) | S2 |
| Citations — Field Landmarks + Latest frontier | **OpenAlex** (`openalex.citation_relations`) | **OpenAlex** |

**OpenAlex owns the citation relation** (`_citation_relations`, build.py:66) —
S2's `citation_relations` runs *only* as a fallback, when OA can't resolve the
seed. The reason is an S2 **API limitation, not a data one**: S2's citation
endpoint is **newest-first with no citation-count sort**, and paging caps at
`_MAX_OFFSET` (8,000, in `_fetch_citers`) — that last page holds 1,000, so
`REACHABLE_CITERS` is exactly **9,000**. So S2 cannot hand you the *most-cited*
citers of a heavily-cited paper — the landmarks are older, buried past the offset
ceiling, and there's no `sort=citations` to reach them; all S2 can do is mine the
newest 9,000 and guess (recency-biased). OpenAlex supports
`sort=cited_by_count:desc` server-side, returning the landmark citers directly
in a couple of cheap calls.

**Consequence (read twice):** the graph's ML **Field Landmarks — the nodes
*and* their sizes — are OpenAlex's**, with all the weaknesses in §1–4 (the
3/15 top-citer overlap, the applied-paper skew, the undercounts). S2's
superior ML citation graph is *not* used here; it can't be surfaced
top-cited-first through S2's live API. Keeping S2 preserves ML quality for the
**seed count, references, and similar** — **not** for the citer landmarks,
which are already OA's inside the hybrid.

The `max(S2, OA)` count merge (`_upgrade_node`) only lifts a node to S2's count
when the same paper is *also* sighted through an S2 relation (a citer that's
*also* a "similar", say) — the exception, not the rule. A plain landmark
citer's count is OA's number. (Side effect: node sizes are on **mixed scales** —
S2-counted references vs OA-counted citers — so a citer isn't size-comparable
to a reference on the same graph.)

### Recovering S2's ML landmark quality — two levers (neither free)

- **(a) S2-hydrate OA's citers' counts.** OA gives the citer *set*; batch-look
  each up in S2 (`POST /paper/batch`, the 429-safe bulk endpoint) via its
  `DOI:`/`ARXIV:` id (`openalex.nodes.resolvable_id` — nearly every citer has
  one) and take `max(OA, S2)`. Two sizes:
  - **(a1) counts-only** — relabel the sizes of the citers OA already chose.
    Fixes node **sizes** and unifies the graph's count scale; ~20 lines and one
    cached batch call, degrades to OA counts if S2 is down (never worse).
  - **(a2) bigger pool + re-rank** — fetch a *larger* OA candidate pool,
    S2-hydrate all, re-rank by the hydrated counts. Additionally recovers
    landmarks OA *has but undercounts* (ranked too low to make the cut).

  Neither recovers landmarks OA lacks the citation *edge* for (the missing-set
  problem — the bulk of the ML gap, per §4), and both re-add a bounded (one
  batch/build) S2 dependency.
- **(b) Ingest S2's bulk citations dataset offline.** The only way to get S2's
  full, sortable ML citation graph. There is **no per-paper bulk endpoint**: the
  live REST `/paper/{id}/citations` is offset-only, capped near `offset + limit ≈
  10k` (empirically `offset=9000&limit=1000` 400s and `offset=8000` serves, so our
  `_MAX_OFFSET = 8000` and the reachable pool is ~9k), newest-first with no
  server-side sort — so a hyper-cited paper's citers past that wall (possibly
  including its most-cited landmarks) are unreachable live, and the token-paged
  bulk *search* endpoint is
  query-based with no `cites:{id}` filter. The complete data exists only as the
  Datasets API **`citations` release** — every citation edge for the *entire*
  corpus (~200M papers → billions of edges, gzipped JSONL, refreshed monthly).
  So (b) means: download that whole dataset, store/index it locally
  (SQLite/parquet), and query your own copy for a seed's citers — which finally
  gives the citation-count sort the live API never offered. A real ingestion
  pipeline (+ periodic refresh + storage), not a live call. (Check the release's
  current size/schema against the [Datasets
  API](https://api.semanticscholar.org/api-docs/datasets) before scoping.)

> **Parked (revisit here).** **(a1)** is the cheap, self-contained candidate —
> deliberately **not** filed as an OnePager ticket yet. It only improves how big
> the ML landmarks *look*, not *which* landmarks appear (that ceiling is OA's
> citation graph — only **(b)** lifts it), so it waits until ML landmark
> fidelity is worth acting on. Reconsider it from this note rather than
> re-deriving the analysis.

## Implications for "drop S2, go OpenAlex-only"

S2 is quietly doing **three** jobs: supplying correct citation counts (via the
`max`), anchoring OA seed resolution, and — the newly-measured one — supplying
the correct **landmark citer set** for ML. So OA-only means:

- **Wins:** rate-limit pain disappears (S2 throttles ~1 req/s keyless);
  cross-source identity/dedup glue (id juggling, `_upgrade_node`, two
  normalizers, OA→S2 fallbacks) largely deletes.
- **Costs:** still need an intra-OA canonical-record heuristic (preprint↔VoR,
  imperfect on generic ML titles); recent-ML-preprint citation counts drop
  ~3–4×; and the ML **"Field Landmarks" relation gets a materially different,
  lower-quality citer set** — unfixable by resolution.

**Decision rule.** If the app is about **graph structure / discovery**
(who-cites-whom shape, exploration), the ML undercount is largely cosmetic and
OA-only is a real simplification win. If **citation magnitude and landmark
ranking in the ML corner** drive the UX (node size, "Field Landmarks",
lecture figure-pool ranking, and especially the recent-publications
frontier — where OA lag bites hardest), it's a visible regression.

## Caveats on the evidence

- **S2 as reference, not ground truth.** S2's counts track Google-Scholar
  ballpark for these papers and OA is the low outlier, so treating S2 as
  closer-to-complete is reasonable — but neither is absolute.
- **Fame bias.** The coverage seeds are well-known papers (chosen so
  resolution isn't the confound). A random long-tail sample could differ.
- **Overlap test is RL-only.** The top-citer overlap needs papers small enough
  (< ~9k citers) to pull S2's full citer list; that limited it to mid-cited RL
  papers — the preprint-native worst case. Vision/NLP giants are too large to
  pull cleanly, though their coverage numbers (§1) undercount similarly.

The raw comparisons live in
[`research/citation_coverage/analyze.ipynb`](../research/citation_coverage/analyze.ipynb) —
re-runnable against the live APIs (slowly; see the study's
[README](../research/citation_coverage/README.md)). See also the
OpenAlex-single-source tradeoff notes and the v5.0.0 Similar-relation removal
in [`history.md`](history.md).
