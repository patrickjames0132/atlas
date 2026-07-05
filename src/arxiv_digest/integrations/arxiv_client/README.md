# `integrations.arxiv_client`

Seed search against arXiv itself — the arXiv API (via the `arxiv` package),
not Semantic Scholar.

> **Being retired.** Seed search is moving to Semantic Scholar (wider coverage
> across venues, not just arXiv preprints), so this package is slated for
> removal in Phase 3 once `services/search` is rebuilt on S2. Its one piece
> needed elsewhere — the arXiv-id regex `ID_RE` — has already moved to the
> `integrations.arxiv` package. What remains here is search itself.

## Why it exists

This is a **different service from Semantic Scholar**, answering a different
question. `semantic_scholar` answers "what's connected to this paper"
(references/citations/similarity) — but you need a starting paper first.
`arxiv_client` is how you find one: a relevance-ranked search across all of
arXiv by keyword, title, or author. Once you pick a result, its arXiv id gets
handed to `semantic_scholar` (as `ARXIV:<id>`) to build the graph.

Because these are two different services, they normalize to two different
shapes: `arxiv_client.papers.to_paper()` produces a lighter dict (no citation
count, no `tldr` — arXiv doesn't have those) than `semantic_scholar.nodes.node()`.
A search hit and a graph node look different on purpose.

## How it's structured

A package, split by concern the same way as `semantic_scholar/`:

```
clauses.py  — date-range + category filter clauses
     ↓
papers.py   — normalizing an arxiv.Result into the app's paper dict
     ↓
search.py   — the shared arxiv.Client + the public entry point, search_arxiv
```

- **`clauses.py`** — `date_clause()` / `category_clause()` build arXiv's
  query-syntax fragments for a year range and a category filter. Named
  `clauses`, not `query` — `search_arxiv`'s own parameter is named `query`, and
  a module of that name would shadow it right where both are needed. (arXiv-id
  detection used to live here as `ID_RE`; it moved to `integrations.arxiv`.)
- **`papers.py`** — `to_paper()` normalizes an `arxiv.Result` into the app's
  paper dict; `_short_id()` (private) strips the version suffix so the same
  paper always keys identically.
- **`search.py`** — the shared `arxiv.Client` (`_client`, private) and the
  public entry point, `search_arxiv()`. It borrows `ID_RE` from the `arxiv`
  package to spot when the search box was handed an id (fetch that exact paper)
  vs. keywords (build a boosted relevance query). Note the local `from ..arxiv
  import ID_RE` vs. the absolute `import arxiv` (the PyPI package) — they
  resolve to different things and coexist only here.

`__init__.py` re-exports `search_arxiv`.

## Design decisions worth knowing

- **One shared `arxiv.Client` for the whole process**, never a fresh one per
  call. The `arxiv` package's client paces itself by remembering its *own*
  last-request time — reusing one instance is what enforces arXiv's ~3-second
  politeness window across every call. A fresh client per call was a real, fixed
  bug: with no memory of the previous request, rapid day-by-day pulls fired with
  no gap and arXiv answered with HTTP 429.
- **The title-boost trick.** arXiv's plain free-text relevance ranks an
  exact-title match ("Attention Is All You Need" by its own title) surprisingly
  low — often off the first page. The fix: OR a quoted-title clause with an
  abstract term-group, both explicitly field-prefixed (a bare unprefixed term
  group is malformed and arXiv returns an empty feed). The user's raw text has
  quotes and parens stripped first so it can't break out of that structure.

## Who uses it, and how/why (traced, not yet ported)

- **`services/search.py`** — `arxiv_search()` is a direct passthrough to
  `search_arxiv()`, the live (non-cached) half of seed search. **This is the
  consumer that retires the package:** when `services/search` moves to S2, this
  call goes, and `arxiv_client` with it.

(The `ID_RE` consumers — `services/graph.py`, `routes/graph.py` — now reach for
`arxiv.ID_RE`, not this package; see the `arxiv` package's README.)

## Testing

`test_papers.py`, `test_clauses.py`, `test_search.py`. `arxiv.Result` objects
are built for real (the installed package's class takes plain keyword args, so
no hand-rolled fakes); the shared `_client` is swapped for a stub that records
every `arxiv.Search` it's given, so query construction can be asserted on with
no network. (The `ID_RE` tests moved to the `arxiv` package's `test_ids.py`.)
