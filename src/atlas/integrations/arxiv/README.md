# `integrations.arxiv`

Everything the app derives directly from arXiv itself: arXiv-**id detection**,
figures + full text via [ar5iv](https://ar5iv.org) (arXiv's LaTeX→HTML
renderer), and a paper's own **category tags** via arXiv's export API.

## Why it exists

Three arXiv-specific jobs, all kept for arXiv papers only (the same call we made
to keep ar5iv rather than go pure-PDF):

- **`ID_RE`** — recognizing a bare or URL-wrapped arXiv id (`2406.12345`,
  `hep-th/9901001`, `https://arxiv.org/abs/…`), so a pasted id/link routes
  straight to that exact paper instead of a keyword hunt or a mis-typed
  Semantic Scholar `paperId`.
- **ar5iv rendering** — Semantic Scholar gives abstracts and TL;DRs but not a
  paper's figures or its full body text. ar5iv fills both gaps by rendering the
  paper's own LaTeX source to HTML, which this package fetches once and extracts
  two different things from: figures + captions (for the detail panel) and
  readable body text (for the agentic Q&A tool). It's the *preferred* source,
  not the only one anymore: papers with no ar5iv render (journal papers, failed
  conversions) fall back to pymupdf mining of their open-access PDF —
  `services/pdf`, a consumer-side fallback that changes nothing here.
- **a paper's own category tags** — Semantic Scholar doesn't carry a paper's
  arXiv category codes (`cs.LG`, `math.PR`, …) either. arXiv's export API
  (a different host from ar5iv, built for exactly this per-id metadata lookup)
  supplies the raw codes; `vocab.name_for` labels them for the detail panel.

**This package was `ar5iv`, renamed to `arxiv` (2026-07-05) to be the single
home for arXiv-derived code.** `ID_RE` moved in from the separate `arxiv_client`
package — arXiv *search*, which was retired in favour of Semantic Scholar and
deleted (along with the PyPI `arxiv` dependency it was the only user of). Its id
regex was still needed elsewhere, so it was homed here rather than deleted with
the rest.

The ar5iv side itself merges what were two independent modules in the original
app (`figures.py` + `fulltext.py`), which already shared a fetch and TTL via one
reaching into the other's internals; a shared `client.py` fixes that at the root.

## How it's structured

```
ID_RE           — the arXiv-id regex, at the package root (__init__.py)

client.py       — fetch_html, fetch_image, is_ar5iv_url, the shared cache TTL
     ↓
figures.py      — extracts {image, caption} pairs from the render
fulltext.py     — strips the render to readable body text

categories.py   — a paper's own category codes, via arXiv's export API (its
                  own host + client — unrelated to ar5iv's client.py above)
vocab.py        — the bundled taxonomy: what categories exist + their labels
```

- **`ID_RE`** lives at the package root, so consumers just do
  `from ..integrations import arxiv` / `arxiv.ID_RE`. It's a plain compiled
  regex — group 1 is the bare id — used with `.fullmatch` (is the whole string
  an id?) or `.search` (is there an id inside this text?) depending on caller.
- **`client.py`** — `fetch_html()` (the raw ar5iv fetch), `fetch_image()` +
  `is_ar5iv_url()` (the same-origin image proxy's fetch + SSRF-safe host
  allowlist), and `CACHE_TTL` (30 days — ar5iv renders are static). `AR5IV_HOST`
  / `BASE_URL` keep the ar5iv name because they *are* ar5iv.org — the package
  name is the arXiv umbrella; the transport still talks to the ar5iv service.
- **`figures.py`** — `get_figures()`, backed by `_FigureParser` (tracks
  `<figure>` nesting so a stray inner figure can't overwrite the outer one's
  image) and `_abs_url()`. Both private.
- **`fulltext.py`** — `get_fulltext()` and `html_to_text()`, backed by
  `_TextParser`. `html_to_text()` is public because it's reused outside this
  package — see below. **Equations survive:** ar5iv carries each formula's
  source LaTeX in the MathML `alttext`, and `get_fulltext()` passes
  `keep_math=True` so `_TextParser` lifts that LaTeX inline (`$…$` / `$$…$$`
  for a displayed equation) instead of dropping the formula — a reader
  (researcher, intuition lecture) sees the paper's actual math, which the
  frontend renders with KaTeX. The MathML subtree is always suppressed either
  way. `html_to_text()` defaults to `keep_math=False`, so the web-page ingester
  below is unaffected.
- **`categories.py`** — `fetch_categories()` (the raw arXiv export API call,
  parsed from its Atom feed with stdlib `xml.etree.ElementTree`) and
  `get_categories()` (labels + caches). Its own `_USER_AGENT` and host
  constant — `client.py`'s are ar5iv-specific and this hits
  `export.arxiv.org`, a different service entirely.
- **`vocab.py`** — see "Category taxonomy" below.

`__init__.py` re-exports `ID_RE`, `get_categories`, `get_figures`,
`get_fulltext`, `html_to_text`, `is_ar5iv_url`, and `fetch_image`.

## Design decisions worth knowing

- **`html_to_text()` isn't really arXiv-specific — a known layering tension,
  not resolved here.** It's a generic "strip HTML to readable text" also used by
  `library/sources.py` (not yet ported) on arbitrary ingested *web pages*. It
  stays here for now (one other consumer); if Phase 3 shows it's needed more
  broadly it may be extracted into a standalone module then — not speculatively
  now.
- **The ar5iv fetches reuse `config.providers.s2.timeout`** — Semantic Scholar's timeout,
  not a dedicated ar5iv one. A pre-existing quirk carried over rather than
  inventing a config field with no documented need yet.
- **A miss is cached too.** When ar5iv has no render (404 — a LaTeX-conversion
  failure or PDF-only submission), both `get_figures()` and `get_fulltext()`
  cache `{"available": False, ...}` rather than retrying on every panel open.
  `get_categories()` follows the same rule for a bad/withdrawn id — arXiv's
  export API answers a miss with HTTP 200 and zero `<entry>` elements, not a
  404, so `fetch_categories()` returns `None` rather than raising.

## Who uses it, and how/why

- **`services/graph/build.py`** — `arxiv.looks_arxiv()` (which wraps
  `ID_RE.fullmatch`) to decide whether a seed is an arXiv id (look it up as
  `ARXIV:<id>`) or a raw S2 `paperId` — the discrimination that lets
  re-seeding land on any node, arXiv or not.
- **`routes/graph.py`** — `arxiv.ID_RE.search()` to pull an id out of pasted
  text (extraction, not discrimination — hence `search`, where
  `looks_arxiv` uses `fullmatch`), then `looks_arxiv()` for the same
  prefix-or-not lookup as the graph build; plus the detail panel's figures
  (`get_figures()`), category tags (`get_categories()`), and the
  `/api/figure_proxy` route (`is_ar5iv_url()` to allowlist, `fetch_image()`
  to relay) so the browser never talks to ar5iv directly and the proxy
  can't be abused as an open relay.
- **`agents/researcher/tools.py`** — the `read_paper` tool calls `get_fulltext()`
  for a paper's actual content beyond the abstract/TL;DR, and `show_figure`
  calls `get_figures()`.
- **`agents/lecturer/main.py`** — the INTUITION lecture calls `get_fulltext()`
  (`_seed_fulltext`) to read the seed paper and teach it in chapters with its
  real equations, and `get_figures()` for every mode's figure pool.
- **`services/sources/extract.py`** — calls `html_to_text()` directly (not
  `get_fulltext()`) to turn an ingested web page into searchable text — the
  one caller with nothing to do with ar5iv or arXiv (see the layering note).

## Category taxonomy — `vocab.py` — and a paper's own tags — `categories.py`

The arXiv **category taxonomy**: the ~155 arXiv codes (`cs.LG`, `math.PR`, …)
grouped into 8 top-level areas, each a `{code, name}` pair
(`cs.LG` → "Machine Learning"). Sourced once from
<https://arxiv.org/category_taxonomy> and bundled here as `taxonomy.json`.

It lives in *this* package (rather than a separate taxonomy package) because
it's arXiv-specific, the same reason `ID_RE` and ar5iv do — each provider owns
its own controlled vocabulary. Semantic Scholar's parallel (coarser) one is
`semantic_scholar.vocab`.

- **`vocab.name_for(code)`** — the code → display-name lookup
  (`cs.LG` → "Machine Learning"), for labelling a paper's *own* tags. Returns
  `None` for a code arXiv has since retired/renamed out of the taxonomy;
  `categories.get_categories()` falls back to the bare code rather than
  dropping it. Reads a private `@lru_cache`'d `_data()` that parses
  `taxonomy.json` once.

  (The `groups()` area-tree and `valid_codes()` accessors were removed in
  v5.1.0 — they fed the retired arXiv-category *search filter* and its
  `/api/taxonomy/arxiv` endpoint; only per-paper tag labelling remains.)

`vocab` only answers "what categories exist" and "what's this code called" —
it has no idea what any *specific paper* is tagged with. That's
`categories.py`'s job: `get_categories(arxiv_id)` fetches the paper's own
codes from arXiv's export API (`https://export.arxiv.org/api/query` — a
different host from ar5iv, and the *only* source for this field; S2 doesn't
carry it) and labels each one via `vocab.name_for`, caching the result
(`{"available", "categories": [{"code", "name"}]}`) the same way
`figures.py`/`fulltext.py` cache theirs.

Design notes:
- **The taxonomy is static bundled data**, not a runtime fetch — it changes
  maybe once a year, so shipping the file means no network call and no cache
  to reason about for "what exists". A paper's *own* tags are the opposite —
  genuinely per-paper data that only arXiv's live metadata has — hence the
  separate `categories.py` fetch.
- **`fetch_categories()` returns `None`, not raises, for an unresolvable id** —
  arXiv's export API answers a bad/withdrawn id with HTTP 200 and an empty
  feed (zero `<entry>` elements), never a 404. The route degrades that (and
  any real HTTP/network failure) to `available: false` either way.
- **`get_categories()` dedupes by display name, not by code.** Six pairs in
  the taxonomy are different codes for the same subject cross-listed under
  two top-level areas and happen to share one name (`cs.LG`/`stat.ML`, both
  "Machine Learning"; also `cs.IT`/`math.IT`, `cs.NA`/`math.NA`,
  `cs.SY`/`eess.SY`, `math.MP`/`math-ph`, `math.ST`/`stat.TH`). A paper
  cross-listed in both of a pair would otherwise show the identical label
  twice; only arXiv's first-listed code of the pair survives.

## Testing

This package contributes `test_ids.py` (`ID_RE` against bare/versioned/old-style
/URL-wrapped ids and a keyword non-match), `test_vocab.py` (the taxonomy: 8
areas, `cs.LG` → "Machine Learning", `valid_codes()` covers exactly the codes in
`groups()`, memoization, `name_for` known/unknown codes), `test_categories.py`
(labelling, the bare-code fallback for an unrecognized code, the
no-entry/blank-id misses, cache + refresh, and `fetch_categories` parsing a
real Atom feed shape), plus `test_client.py`, `test_figures.py`,
`test_fulltext.py`. `client.fetch_html` is faked at the module boundary so
`figures`/`fulltext` tests never touch real HTTP; `test_client.py` and
`test_categories.py` each fake `urllib.request.urlopen` directly for their own
host.
