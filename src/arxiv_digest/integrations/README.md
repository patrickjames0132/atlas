# `integrations`

External-service clients — every module that talks to a remote API. Modules
here own their own HTTP plumbing, rate-limit etiquette, and caching keys;
the `services` package (Phase 3) composes them into domain logic.

- **`semantic_scholar/`** — the S2 Academic Graph + Recommendations client
  (the paper-data backbone). Its own package; see its own README.
- **`arxiv_client/`** — seed search against arXiv itself (finds the starting
  paper; `semantic_scholar` builds the graph around it once picked). Its
  own package; see its own README.
- **`ar5iv/`** — everything from ar5iv (arXiv's LaTeX→HTML renderer): a
  paper's figures/captions and its full body text. Its own package (merges
  the original app's separate `figures.py` and `fulltext.py`); see its own
  README.
- **`huggingface.py`** — code & artifact links from Hugging Face Papers. See
  below.
- **`taxonomy.py`** — not yet ported (rest of Phase 2).

## `huggingface.py`

### Why it exists

Papers with Code sunset into Hugging Face Papers, so HF is now the place
that maps an arXiv id to runnable implementations: a community-linked
GitHub repo, plus the models, datasets, and Spaces that cite the paper.
This is what powers the detail panel's "code & artifacts" section — one
call to `https://huggingface.co/api/papers/{arxiv_id}` returns all of it.

### How it's structured

One module, no package needed — a single external service with one shape
of data, unlike `ar5iv` (two genuinely different extractions from the same
render) or `semantic_scholar` (several distinct endpoint families):

- **`_fetch_paper()`** — the raw HTTP call, 404-as-miss.
- **`_as_int()` / `_repo_items()`** — defensive normalization helpers. HF's
  JSON has a lot of "field might be missing, null, or malformed" surface
  (an unindexed field, a non-numeric count, a junk entry in a linked-repo
  list); these two absorb that so `get_code_links()` doesn't have to.
- **`empty_result()`** — the full response envelope with nothing in it.
  Public (not `_empty` as in the original) — `routes/graph.py` (not yet
  ported) reaches for it directly as a fallback when the main lookup fails
  unexpectedly, so it's genuinely cross-module, not single-file-private.
- **`get_code_links()`** — the public entry point: cache lookup, fetch on
  miss, normalize, cache the result (including a miss).

### Design decisions worth knowing

- **A miss is cached too**, same pattern as `ar5iv`: a paper HF has never
  indexed gets `{"available": False, ...}` cached for a day, so it costs
  one request a day rather than one per detail-panel open.
- **`_HF_HOST` is private** (renamed from a public `HF_HOST` in the
  original) — unlike `ar5iv`'s `AR5IV_HOST`, nothing outside this file
  ever references it. Public-by-convention (matching a similarly-shaped
  neighbor file) isn't a reason to keep something public if nothing
  actually needs it to be.
- **Reuses `config.s2.timeout`** for its own HTTP calls — the same
  pre-existing quirk as `ar5iv` (a Semantic Scholar setting borrowed for
  an unrelated external service). Left as-is rather than inventing a new
  per-service config field with no documented need yet.
- **`_repo_items()` caps at 5 items per kind** (`_MAX_ITEMS`) — the
  `totals` dict still reports the *real* total count HF knows about, so
  the detail panel can show "254 models" even though only 5 are listed.

### Who uses it, and how/why (traced, not yet ported)

- **`routes/graph.py`** — `GET /api/paper/<id>/code`, the detail panel's
  code & artifacts section. Wraps the call in a bare `except Exception`
  (deliberately broad — "HF down/slow, degrade gracefully, don't 500 the
  panel") and falls back to `huggingface.empty_result()` directly when
  something goes wrong, which is exactly why that function needed to be
  public rather than private.

### Testing

`test_huggingface.py` — 8 tests, ported from the original app's existing
suite (this file already had one, unlike most of Phase 2 so far) plus two
new ones covering `empty_result()` directly. HTTP is faked at
`_fetch_paper` for the normalization tests, and at
`urllib.request.urlopen` for the 404-as-cached-miss path.
