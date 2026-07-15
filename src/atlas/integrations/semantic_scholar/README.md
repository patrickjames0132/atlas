# `integrations.semantic_scholar`

The one place in the entire app that talks to Semantic Scholar. Every paper
title, abstract, citation relationship, and similarity score the app ever
shows comes through this package.

## Why it exists

arXiv Atlas's core design bet is to **never store a paper corpus**. There's
no local database of "all papers" — instead, every time you explore a
paper, the app asks Semantic Scholar live: "what does this cite, what cites
it, what's similar to it?" and draws the graph from the answer. Without
this package, there is no graph — it's the thing that turns a seed paper
into an explorable neighborhood.

## How it's structured

```
client.py     — talks to S2 over HTTP: throttling, 429 retries, the S2Error type
     ↓
nodes.py      — translates S2's raw JSON into the app's own "node" shape
     ↓                (id, title, abstract, year, citation count, url, ...)
traversal.py  — get_papers/get_paper, references, citations, recommendations
search.py     — search_papers (free-text, no source paper needed)
corpus/       — the offline S2 citations corpus (bulk Datasets releases → local
                Parquet); its citation_relations is preferred over traversal's
                recency-biased live one when a corpus is ingested
```

A package (not a flat module) split by concern, four files instead of one
~400-line file:

- **`client.py`** — the plumbing: build the HTTP request, throttle it, retry
  on 429 with exponential backoff, raise `S2Error` for anything else that
  fails. Nothing here uses a third-party HTTP dependency — stdlib
  `urllib` keeps the client tiny.
- **`nodes.py`** — the translator: `node()` is the *single* place a raw S2
  paper object becomes the app's own dict shape. Every downstream consumer
  (graph canvas, teacher, frontend detail panel) agrees on one shape
  because they all ultimately get it from here, regardless of which S2
  endpoint produced the raw data. Also holds `from_papers()`, a small
  shared helper (list of raw papers → `[{"node": ...}, ...]`, skipping
  unresolved entries) used by both `recommendations()` and `search_papers()`
  — they had identical loops before this was factored out.
- **`traversal.py`** — "what's connected to this paper?": `references()`
  (blue nodes — what it cites), `citation_relations()` (splits citers into
  **landmark** green nodes and **latest** light-green nodes — the citation path
  **when the S2 provider is selected**, see the citations section below),
  `citations()` (the single-relation landmark view for on-demand graph
  expansion), `recommendations()` (SPECTER2 embedding similarity — now used
  **only** by the researcher's `expand_node`; the seed-graph *Similar* relation
  was retired in v5.0.0), plus `get_papers()`/`get_paper()` to hydrate full
  details for known ids.
- **`search.py`** — "search all of S2 for X," with no source paper at all.
  Exists specifically because citation/similarity traversal is
  *lineage-biased*: a brand-new paper citing a 2017 seed has no citations
  of its own yet, so no amount of hopping from the seed will ever surface
  it. Free-text search is the only way to reach that kind of paper.

`__init__.py` re-exports the full public API (`S2Error`, `get_papers`,
`get_paper`, `references`, `citations`, `citation_relations`,
`recommendations`, `search_papers`),
so `from ..integrations import semantic_scholar as s2` and `s2.get_papers(...)`
work exactly as if this were still one file — nothing importing this
package needs to know it's a package internally.

## Design decisions worth knowing

- **The throttle is a global, process-wide lock — not per-call, not
  per-feature.** `client.py`'s `_throttle_lock`/`_last_request` are module
  state shared by every caller (graph build and agent expansion can fire
  concurrently). There's only one S2 rate-limit budget to protect, no
  matter how many features are hitting it at once, so the throttle has to
  be global.
- **Batch over single-fetch.** `get_papers()` always uses `POST
  /paper/batch` (chunked at 500 ids, S2's cap), never the single-paper GET
  — which 429s almost immediately for unauthenticated callers.
- **Retry only on 429; fail fast on everything else.** Any other HTTP
  error or network failure raises `S2Error` immediately — the one
  exception type this whole package raises, which routes (once ported)
  catch and turn into an HTTP 502.
- **Underscore-prefixed names are genuinely single-file-private.**
  `_neighbors`, `_year_range`, `_BATCH_MAX` are each used by exactly one
  file. Everything called *across* the package's own submodules
  (`throttle`, `headers`, `request`, `quote`, `node`) has no underscore —
  splitting a file into a package changes what counts as "private."
- **No single-letter variables.** `paper` not `p`, `exc` not `e`,
  `http_request`/`response` not `req`/`resp`, `year_from`/`year_to` not
  `lo`/`hi`.

## Citations: landmark vs latest (the S2 provider's citation path)

> **Since v5.0.0 a graph is built from one provider.** When the user picks
> **Semantic Scholar** in the header dropdown, `citation_relations()` is the
> **primary** citation path (not a fallback). It carries a known interim
> limitation — the ~10k offset recency bias below — that OpenAlex avoids with
> server-sorted `cites:` queries and that the offline S2 **citations corpus**
> will eventually fix. (In v4.x this path was the OpenAlex-can't-resolve
> fallback; the v5.0.0 provider split promoted it back to a first-class path.)

A seed's citers are split into **two disjoint relations** by
`citation_relations()`, both built from **one paged citer fetch**
(`_fetch_citers(deep=True)`):

- **latest** (light-green nodes) — citers published within the rolling last
  `_LATEST_WINDOW_MONTHS` (12) months, by `pub_date`, newest-first. Capped at
  `config.graph.latest_limit`.
- **landmark** (green nodes) — everything else, the most-cited *historic* citers.
  Chosen by the injected `landmark_select` rule (below), falling back to a flat
  `landmark_limit`.

**When S2 gives no `publicationDate`, `year` decides** (`_is_latest`). A citer
from a year *after* the cutoff's year is in the window whatever month it came
out; only the cutoff's own year is ambiguous (January is outside, December
inside) and stays a landmark — a landmark misfiled as frontier is the worse
error. Without this, a **2026** citer with no date got filed as a *historic*
landmark, which is nonsense for a paper months old; those then shared one x (no
month → the year's gridline) and drew a bare vertical line at the graph's right
edge whenever the Latest chip was off. OpenAlex hit the same trap and answered it
harder — it splits by year outright, its dating being coarser still. The `latest`
sort key gets the same fallback (`_latest_order`: a year-only citer sorts as Jan 1
of its year, exactly where the timeline draws it), so the reveal order and the
on-screen order agree.

### Choosing the landmark band (`landmark_select`)

`citation_relations` takes an optional **`LandmarkSelectFn`** — a rule handed the
*ranked* landmark pool's citer years, answering with the **indices** to ship; its
pick wins over the flat `landmark_limit`. `services/graph`'s `build.py` passes
`budget.density_selection`. A parameter rather than an import, so `integrations`
stays below `services` in the dependency order (the same shape as OpenAlex's
`BandStartFn`); years in, indices out, because the rule only reasons about *when*
citers were published — the entries stay here.

This exists because **this path can't use the model the other paths use, and
doesn't need to.** The landmark budget is normally *predicted* from the seed's age
and citation count, which works where the pool is all-time-ranked (OpenAlex; the
offline corpus) — those push a ship count into a sorted query and must know it
before they hold any citers. Here the pool is already in memory by trim time, so
the band can be chosen from the real data.

And it must be, because a count can't express the right answer. A count keeps a
**prefix** of the ranking, and DQN's prefix is all one era: rank 29 exhausts the
per-year cap on 2020, and 2024–2025 — 2155 citers sitting in the pool — never
appear, leaving an 18-month hole before the Latest frontier. `density_selection`
bands the ranking by year instead (twelve per year, skip the full ones), shipping
84 across 2019–2025 with no hole and the same "no year over the cap" guarantee.
It's the local equivalent of the per-year bands OpenAlex gets from its query —
S2's `/citations` has no year filter, so the banding happens over the ranking.
See `services/graph/budget.py`'s module docstring.

### Deep paging

S2 lists citers newest-first, and one page is only 1000 citers. For a heavily-
cited seed that page can span *less than a year*. So the seed build **pages** the
whole reachable list (offsets 0, 1000, 2000, …), stopping only at the list's end
or the `_MAX_OFFSET` ceiling. Graph expansion (`citations()`, `deep=False`) stays
one page — it wants the tip, fast.

`_MAX_OFFSET` is **8000**, not 9000: verified live 2026-07-15, S2 400s a page whose
window reaches ~10k (`offset=9000&limit=1000` fails on two different seeds, while
`offset=8000` serves), so the reachable pool tops out at ~9k citers.

**Why it pages the whole list, not just the `latest` window** (v5.5.0). It used to
stop at the first page holding no in-window citer — the window was covered, and the
boundary page's overshoot was meant to seed the landmark "middle band". On a
hyper-cited seed that quietly gutted the landmark relation. Measured live on DQN:
page 1 holds exactly *one* in-window citer and page 2 holds none, so paging stopped
at offset 2000 with a pool covering 2024–2026, and "Field Landmarks" ranked whatever
recent survey sat in the overshoot. The full reachable list runs back to **2019** and
holds Conservative Q-Learning, Decision Transformer, and Dota 2 — six-sevenths of it
was simply never fetched. Paging on leaves `latest` byte-identical (every deeper page
is older than the window) and buys the landmark relation a pool worth ranking. It
costs a slower **cold** build, scaling with the citer list: measured authenticated,
QMIX 4 pages / ~8s and DQN 9 pages / ~15s, against ~3 pages before. Snapshots cache
for a day and the build's progress bar covers the wait.

**Known limit of the *live* S2 path:** the offset ceiling is a hard wall. DQN's
2013–2018 citers — its actual giants (AlphaGo, A3C, Rainbow) — are unreachable at
any page count, so the landmark relation is the most-cited citers *within the
reachable ~9k*, not the full citation history. Beating that wall was v3.1.0's
`_mined_landmarks` (harvest citers' reference lists, co-citation rank, verify),
retired in v4.0.0 when OpenAlex's sorted `cites:` made it redundant; the corpus is
its replacement.

**The fix — the offline citations corpus (`corpus/`).** When a corpus release is
downloaded and ingested (`config.storage.s2_corpus_dir` set, a `CURRENT` release
present), `build.py`'s `_traverse_s2` calls `corpus.citation_relations` **first**
and only falls back to `traversal.citation_relations` (the recency-biased live
path above) when the corpus is absent or can't resolve the seed. The corpus holds
every citation edge with the citers' own counts, so it returns landmark citers
**citation-sorted across all history** — the ranking the live API can't give. See
[`corpus/README.md`](corpus/README.md).

## Relation ordering (what each traversal returns — and the slider walks)

Every relation comes back **already ranked**, by the one key that fits *its*
meaning. The frontend shows a modest prefix and reveals more on demand — the
per-relation count slider walks exactly this order, no re-query — so the
order the backend returns *is* the order the user reveals through:

| Relation | Returned by | Ordered by |
|----------|-------------|-----------|
| references | `references()` | citation count — most-cited ancestors first |
| `citation` (landmark) | `citation_relations()` landmark half | citation count — biggest landmarks first |
| `latest` | `citation_relations()` latest half | `pub_date`, newest first |
| similar | `recommendations()` | S2 embedding similarity, as returned |

Each uses **one** key — *popularity* for references/landmarks, *recency* for
`latest`, *similarity* for similar — never a blended score, so "landmark = the
giants" and "latest = the freshest" stay honest. (If landmark order should ever
reward recency too, that's a *velocity* key — `citation_count / age` — a
deliberate swap, not the default.)

## Field lists: three tiers on purpose

`nodes.py` defines what each request asks S2 for: `DETAIL_FIELDS` (one
paper, hydration — abstract/tldr/authors), `NEIGHBOR_FIELDS` (the many
nodes of a traversal — summary-light, hydrated lazily on click), and
`SEARCH_FIELDS` = neighbors + `authors.name` (search + title-match hits
render in a pick-a-paper list, where authorship is how humans recognize a
paper; the ~65 anonymous dots of a graph don't need it).

## Who uses it, and how/why

- **`services/graph.py`** — when the graph is built with `provider="s2"`,
  `build_graph()`'s `_traverse_s2` calls one `get_paper()` to hydrate the seed,
  then `references()` + `citation_relations()` for the graph's relations
  (references, landmark citations, latest citations). It **no longer calls
  `recommendations()`** — the *Similar* relation was retired from the build in
  v5.0.0. Also uses `arxiv.looks_arxiv` (from `integrations.arxiv`) to decide
  whether the seed reference needs an `ARXIV:` prefix, or is already a raw S2
  paperId.
- **`agents/traversal.py`** — wraps `references()`/`citations()`/
  `recommendations()`/`search_papers()` behind its own day-long cache (see
  `storage/README.md`) — this *is* the mechanism behind the agentic Q&A
  tools `expand_node` and `search_papers`.
- **`teacher/tools.py`** — calls `get_paper()` to lazily hydrate a neighbor
  node's abstract/tldr on demand, only when the agent's `read_paper` tool
  needs detail that a light-field neighbor node doesn't carry.
- **`routes/graph.py`** — two HTTP entry points: `/api/graph` (via
  `services/graph.py`) and `/api/paper/<id>` (calls `get_paper()` directly
  to hydrate a clicked node's detail panel). Both catch `S2Error` and turn
  it into an HTTP 502 for the frontend.

None of these are ported yet, but because the public API is unchanged,
none of them will need a single import edit when we get there.

## Fields of study — `vocab.py`

S2's **fields of study**: its own ~20 coarse top-level subjects
(`Computer Science`, `Mathematics`, …) — much coarser than arXiv's ~155
categories. This is the vocabulary the **seed-search filter** uses: S2's
`/paper/search` filters on exactly these (`fieldsOfStudy`).

It lives in *this* package because it's S2's vocabulary — each provider owns its
own (arXiv's finer one is `arxiv.vocab`), rather than a shared taxonomy package.

- **`vocab.fields()`** — the fields, alphabetical, for populating the picker.
- **`vocab.valid_fields()`** — a `frozenset` of them, for validating a submitted
  filter.
- Backed by an inline `FIELDS` tuple — a small, fixed, S2-defined list, so no
  data file (unlike arXiv's bundled JSON); each value is already its own
  human-readable label.

**Casing is Title Case** (`"Computer Science"`), matching what S2 returns on
paper objects and accepts in the `fieldsOfStudy` filter. If it ever differs live,
`vocab.FIELDS` is the one tuple to edit. `search.search_papers` forwards a
`fields_of_study` filter straight to `fieldsOfStudy`; its values come from here.

## Testing

Split to mirror the source layout: `test_client.py`, `test_nodes.py`,
`test_traversal.py`, `test_search.py`, and `test_vocab.py` (the ~20 fields in
alphabetical order; `valid_fields()` rejects junk and arXiv codes) — no network
(HTTP is faked at `client.request` or, for `client.py` itself, at
`urllib.request.urlopen`).
