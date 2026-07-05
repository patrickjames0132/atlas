# `integrations.ar5iv`

Everything the app gets from [ar5iv](https://ar5iv.org) — arXiv's LaTeX→HTML
renderer.

## Why it exists

Semantic Scholar gives abstracts and TL;DRs but not a paper's figures or its
full body text. ar5iv fills both gaps by rendering the paper's own LaTeX
source to HTML — which this package fetches once and extracts two different
things from: figures + captions (for the detail panel) and readable body
text (for the agentic Q&A tool that reads a paper's actual content).

**This package merges two previously-independent modules** (`figures.py`
and `fulltext.py`) — they already shared a fetch function and a cache TTL
constant via one reaching directly into the other's private internals
(`fulltext.py` called `figures._fetch_html()` and aliased
`figures._FIG_TTL`). That's exactly the kind of cross-module reach our
naming convention flags: not single-file-private, so it shouldn't have had
an underscore. Merging them and giving both a shared `client.py` fixes it
at the root instead of just renaming around it.

**Unlike the `semantic_scholar`/`arxiv_client` splits, this one changes the
external interface.** Those were *one* module split into several — callers
kept importing the same package name. This is *two* modules merged into
one, so callers' imports change too: `from ..integrations import figures`
+ `from ..integrations import fulltext` becomes one
`from ..integrations import ar5iv`. Worth remembering when we port the
files that call this (see below) — their imports need updating, not just
their config references.

## How it's structured

```
client.py    — fetch_html, fetch_image, is_ar5iv_url, the shared cache TTL
     ↓
figures.py   — extracts {image, caption} pairs from the render
fulltext.py  — strips the render to readable body text
```

- **`client.py`** — `fetch_html()` (the raw ar5iv fetch), `fetch_image()` +
  `is_ar5iv_url()` (the same-origin image proxy's fetch + SSRF-safe host
  allowlist — these moved here from `figures.py` since they're generic
  transport, not figure-specific), and `CACHE_TTL` (30 days — ar5iv renders
  are static, so a long TTL is safe, and both `figures.py` and `fulltext.py`
  share the same freshness assumption).
- **`figures.py`** — `get_figures()`, backed by `_FigureParser` (tracks
  `<figure>` nesting so a stray inner figure can't overwrite the outer
  one's image) and `_abs_url()` (resolves an ar5iv-relative image path
  against the host). Both private — single-file use.
- **`fulltext.py`** — `get_fulltext()` and `html_to_text()`, backed by
  `_TextParser` (keeps paragraph/heading/list-item text, drops math/
  scripts/figures/citations). `html_to_text()` is public because it's
  reused outside this package entirely — see below.

`__init__.py` re-exports `get_figures`, `get_fulltext`, `html_to_text`,
`is_ar5iv_url`, and `fetch_image`.

## Design decisions worth knowing

- **`html_to_text()` isn't really ar5iv-specific — and that's a known
  layering tension, not resolved here.** It's a generic "strip HTML down to
  readable text" function that also gets used by `library/sources.py` (not
  yet ported) to extract text from an arbitrary ingested *web page* — no
  ar5iv, no arXiv, nothing this package's transport layer does. It stays
  here for now because that's where it already lives and there's only one
  other consumer; if Phase 3 (`library/sources.py`) reveals it's needed
  more broadly, it may be worth extracting into a standalone, dependency-
  free module at that point — deliberately not doing that now, before we've
  actually seen how it's used there.
- **Both fetch functions reuse `config.s2.timeout`** — Semantic Scholar's
  timeout setting, not a dedicated ar5iv one. A pre-existing quirk carried
  over as-is rather than inventing a new config field for a second service
  that doesn't have a documented need for its own timeout yet.
- **A miss is cached too.** When ar5iv has no render for a paper (404 — a
  LaTeX-conversion failure or a PDF-only submission), both `get_figures()`
  and `get_fulltext()` cache `{"available": False, ...}` rather than
  retrying every time that paper's detail panel opens.

## Who uses it, and how/why (traced, not yet ported)

- **`routes/graph.py`** — the detail panel's figures (`get_figures()`), and
  the `/api/figure_proxy` route (`is_ar5iv_url()` to allowlist the request,
  `fetch_image()` to relay it) so the browser never talks to ar5iv
  directly and the proxy can't be abused as an open relay.
- **`teacher/tools.py`** — the agentic Q&A `read_paper` tool calls
  `get_fulltext()` when it needs a paper's actual content (methods,
  results, numbers) beyond what the abstract/TL;DR gives it.
- **`library/sources.py`** — calls `html_to_text()` directly (not
  `get_fulltext()`) to turn an ingested web page into searchable text. This
  is the one caller that has nothing to do with ar5iv or arXiv at all — see
  the layering note above.

## Testing

118 tests project-wide; this package contributes `test_client.py`,
`test_figures.py`, `test_fulltext.py` (none of these three had a dedicated
test file in the original app). `client.fetch_html` is faked directly at
the module boundary, so `figures`/`fulltext` tests never touch real HTTP;
`test_client.py` itself fakes `urllib.request.urlopen`.
