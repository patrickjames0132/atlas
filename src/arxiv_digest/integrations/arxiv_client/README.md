# `integrations.arxiv_client`

Seed search against arXiv itself — the arXiv API (via the `arxiv` package),
not Semantic Scholar.

## Why it exists

This is a **different service from Semantic Scholar**, answering a
different question. `semantic_scholar` answers "what's connected to this
paper" (references/citations/similarity) — but you need a starting paper
first. `arxiv_client` is how you find one: a relevance-ranked search across
all of arXiv by keyword, title, author, or a pasted id/URL. Once you pick a
result, its arXiv id gets handed to `semantic_scholar` (as `ARXIV:<id>`) to
actually build the graph.

Because these are two different services, they normalize to two different
shapes: `arxiv_client.papers.to_paper()` produces a lighter dict (no
citation count, no `tldr` — arXiv doesn't have those) than
`semantic_scholar.nodes.node()`. A search hit and a graph node look
different on purpose.

## How it's structured

A package, split by concern the same way as `semantic_scholar/`:

```
clauses.py  — id detection (ID_RE) + date-range/category filter clauses
     ↓
papers.py   — normalizing an arxiv.Result into the app's paper dict
     ↓
search.py   — the shared arxiv.Client + the public entry point, search_arxiv
```

- **`clauses.py`** — **`ID_RE`** detects whether the user's input is a bare
  arXiv id or a pasted arxiv.org URL (any of new-style `2406.12345`,
  old-style `hep-th/9901001`, either with a version suffix, optionally
  wrapped in an `http(s)://arxiv.org/abs/` or `/pdf/` URL). If it matches,
  `search_arxiv` fetches that exact paper instead of running a keyword
  search — an explicit id always wins over search filters. **Not
  underscore-prefixed** even though it's a "detail" — `services/graph.py`
  and `routes/graph.py` both reach into it directly to detect a pasted id
  outside of search entirely (e.g. re-seeding the graph), so it's genuinely
  shared, not single-file-private. `date_clause()`/`category_clause()`
  build arXiv's query-syntax fragments for a year range and a category
  filter. The module is named `clauses`, not `query` — `search_arxiv`'s own
  parameter is named `query` (the search string), and a module of that name
  would shadow it right where both are needed.
- **`papers.py`** — `to_paper()` normalizes an `arxiv.Result` into the app's
  paper dict; `_short_id()` (private — only `to_paper` calls it) strips the
  version suffix so the same paper always keys identically.
- **`search.py`** — the shared `arxiv.Client` (`_client`, private — only
  this file touches it) and the public entry point, `search_arxiv()`, which
  detects an id vs. a keyword query and, for keyword queries, builds a
  boosted query (see below).

`__init__.py` re-exports `search_arxiv` and `ID_RE`, so
`from ..integrations import arxiv_client` and `arxiv_client.search_arxiv(...)`
/ `arxiv_client.ID_RE` work exactly as if this were still one file.

## Design decisions worth knowing

- **One shared `arxiv.Client` for the whole process**, never a fresh one
  per call. The `arxiv` package's client paces itself by remembering its
  *own* last-request time — reusing one instance is what actually enforces
  arXiv's ~3-second politeness window across every call. A fresh client per
  call was a real, fixed bug in this app's history: with no memory of the
  previous request, rapid day-by-day pulls fired with no gap and arXiv
  answered with HTTP 429.
- **The title-boost trick.** arXiv's plain free-text relevance ranks an
  exact-title match (searching "Attention Is All You Need" by its own
  title) surprisingly low — often off the first page entirely. The fix:
  OR a quoted-title clause with an abstract term-group, both explicitly
  field-prefixed (a bare unprefixed term group is malformed query syntax
  and arXiv returns an empty feed for it). The user's raw text has quotes
  and parens stripped first so it can't break out of that structure.
- **A real bug found and fixed while writing tests for the first time:**
  `ID_RE` never had a dedicated test file in the original app. Writing one
  surfaced a genuine gap — the regex didn't tolerate a URL scheme
  (`https://`), so pasting a complete URL copied from a browser's address
  bar (`https://arxiv.org/abs/2406.12345`) silently failed the id check and
  fell through to a nonsense keyword search over the whole URL string.
  Fixed by making the scheme optional in the pattern; verified against
  every id format plus a non-id control case before applying it.

## Who uses it, and how/why (traced, not yet ported)

- **`services/search.py`** — `arxiv_search()` is a direct passthrough to
  `search_arxiv()`. This is the live (non-cached) half of seed search:
  "type a title, get arXiv hits ranked by relevance."
- **`services/graph.py`** — reaches into `ID_RE` directly (not
  `search_arxiv`), via a `_looks_arxiv()` helper, to decide whether a
  re-seed reference is an arXiv id (needs an `ARXIV:` prefix before
  Semantic Scholar will accept it) or a raw S2 paperId.
- **`routes/graph.py`** — also reaches into `ID_RE` directly, in
  `_normalize_arxiv_id()`, to strip a pasted arxiv.org URL or version
  suffix down to a bare id before using it as the seed reference. This is
  what makes "paste a link and hit enter" work for *re-seeding* the graph
  from a node, not just the initial search box.

## Testing

Split to mirror the source layout: `test_papers.py`, `test_clauses.py`,
`test_search.py` — 21 tests total. `arxiv.Result` objects are built for
real (the installed package's actual class takes plain keyword args — no
need for hand-rolled fakes); the shared `_client` is swapped for a stub
that records every `arxiv.Search` it's given, so query construction can be
asserted on directly with no network.

(One project-wide fix that came out of this split: two test files across
different packages ended up sharing the basename `test_search.py`. With no
`__init__.py` in the test tree, pytest's default import mode collided on
that. Fixed once, project-wide, by switching pytest to
`--import-mode=importlib` in `pyproject.toml` — it resolves test modules by
full path instead of basename, so this can't recur as more packages split.)
