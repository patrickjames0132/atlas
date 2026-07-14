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
  Capped at `config.graph.cite_limit`. A citer with no `pub_date` competes here.

### Deep paging

S2 lists citers newest-first, and one page is only 1000 citers. For a heavily-
cited seed that page can span *less than a year*, truncating the `latest` window
and missing mid-era citers. So the fallback build **pages** (offsets 0, 1000,
2000, …), stopping at the first page with no in-window citer, the list end, or
the `_MAX_OFFSET` (~10k) ceiling. Graph expansion (`citations()`, `deep=False`)
stays one page — it wants the tip, fast.

**Known limit of the S2 provider:** without OpenAlex's sorted queries it is
newest-first and offset-capped, so a hyper-cited seed's oldest landmarks (past
~10k) are unreachable and the landmark relation is drawn from the most-cited
citers *within the recent ~10k*, not the full citation history. That's the
artifact OpenAlex avoids and the offline citations corpus will fix; picking
OpenAlex in the dropdown sidesteps it today.

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
