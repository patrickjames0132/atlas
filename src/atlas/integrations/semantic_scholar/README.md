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
  (blue nodes — what it cites), `citations()` (green nodes — what cites
  it), `recommendations()` (purple nodes — SPECTER2 embedding similarity),
  plus `get_papers()`/`get_paper()` to hydrate full details for known ids.
  These three relation types are literally the three colors in the graph
  legend.
- **`search.py`** — "search all of S2 for X," with no source paper at all.
  Exists specifically because citation/similarity traversal is
  *lineage-biased*: a brand-new paper citing a 2017 seed has no citations
  of its own yet, so no amount of hopping from the seed will ever surface
  it. Free-text search is the only way to reach that kind of paper.

`__init__.py` re-exports the full public API (`S2Error`, `get_papers`,
`get_paper`, `references`, `citations`, `recommendations`, `search_papers`),
so `from ..integrations import semantic_scholar as s2` and `s2.get_papers(...)`
work exactly as if this were still one file — nothing importing this
package needs to know it's a package internally.

## Design decisions worth knowing

- **The throttle is a global, process-wide lock — not per-call, not
  per-feature.** `client.py`'s `_throttle_lock`/`_last_request` are module
  state shared by every caller (graph build, lecture history backfill,
  agent expansion can all fire concurrently). There's only one S2
  rate-limit budget to protect, no matter how many features are hitting it
  at once, so the throttle has to be global.
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

## Field lists: three tiers on purpose

`nodes.py` defines what each request asks S2 for: `DETAIL_FIELDS` (one
paper, hydration — abstract/tldr/authors), `NEIGHBOR_FIELDS` (the many
nodes of a traversal — summary-light, hydrated lazily on click), and
`SEARCH_FIELDS` = neighbors + `authors.name` (search + title-match hits
render in a pick-a-paper list, where authorship is how humans recognize a
paper; the ~65 anonymous dots of a graph don't need it).

## Who uses it, and how/why

- **`services/graph.py`** — `build_graph()` is the whole point of this
  package's existence: one `get_paper()` to hydrate the seed's rich
  details, then `references()`/`citations()`/`recommendations()` to build
  the three relation types that make up the visible graph. Also uses
  `arxiv.ID_RE` (not this package) to decide whether the seed reference
  needs an `ARXIV:` prefix before hitting S2, or is already a raw S2 paperId.
- **`teacher/lecture.py`** — walks backward through `references()` during
  the "How we got here" history backfill; catches `S2Error` per-hop so one
  failed hop skips that ancestor rather than aborting the whole lecture.
- **`teacher/neighbors.py`** — wraps `references()`/`citations()`/
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
