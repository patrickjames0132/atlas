# `integrations`

External-service clients — every module that talks to a remote API. Modules
here own their own HTTP plumbing, rate-limit etiquette, and caching keys;
the `services` package (Phase 3) composes them into domain logic.

- **`semantic_scholar/`** — the S2 Academic Graph + Recommendations client
  (the paper-data backbone). Its own package; see its own README.
- **`arxiv_client.py`** — seed search against arXiv itself. See below.
- **`fulltext.py`, `figures.py`, `huggingface.py`, `taxonomy.py`** — not yet
  ported (rest of Phase 2).

## `arxiv_client.py`

### Why it exists

This is a **different service from Semantic Scholar**, answering a
different question. `semantic_scholar` answers "what's connected to this
paper" (references/citations/similarity) — but you need a starting paper
first. `arxiv_client` is how you find one: a relevance-ranked search across
all of arXiv by keyword, title, author, or a pasted id/URL. Once you pick a
result, its arXiv id gets handed to `semantic_scholar` (as `ARXIV:<id>`) to
actually build the graph.

Because these are two different services, they normalize to two different
shapes: `arxiv_client._to_paper()` produces a lighter dict (no citation
count, no `tldr` — arXiv doesn't have those) than
`semantic_scholar.nodes.node()`. A search hit and a graph node look
different on purpose.

### How it's structured

One file, four small pure-logic helpers plus the public `search_arxiv()`:

- **`ID_RE`** — detects whether the user's input is a bare arXiv id or a
  pasted arxiv.org URL (any of new-style `2406.12345`, old-style
  `hep-th/9901001`, either with a version suffix, optionally wrapped in an
  `http(s)://arxiv.org/abs/` or `/pdf/` URL). If it matches, `search_arxiv`
  fetches that exact paper instead of running a keyword search — an
  explicit id always wins over search filters. **Not underscore-prefixed**
  even though it's a "detail" — `services/graph.py` and `routes/graph.py`
  both reach into it directly to detect a pasted id outside of search
  entirely (e.g. re-seeding the graph), so it's genuinely shared, not
  single-file-private.
- **`_short_id()`** — strips the version suffix (`v2`) so the same paper
  always keys identically regardless of which version arXiv returned.
- **`_to_paper()`** — normalizes an `arxiv.Result` into the app's paper dict.
- **`_date_clause()` / `_category_clause()`** — build arXiv's query-syntax
  fragments for a year range and a category filter, respectively. Both
  private — only `search_arxiv` calls them.
- **`search_arxiv()`** — the public entry point. Detects an id vs. a
  keyword query, and for keyword queries builds a boosted query (see below).

### Design decisions worth knowing

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

### Testing

`test_arxiv_client.py` — 21 tests. `arxiv.Result` objects are built for
real (the installed package's actual class takes plain keyword args — no
need for hand-rolled fakes); the shared `_client` is swapped for a stub
that records every `arxiv.Search` it's given, so query construction can be
asserted on directly with no network.
