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
- **`huggingface/`** — code & artifact links (GitHub repo, models/datasets/
  Spaces) from Hugging Face Papers. Its own package; see its own README.
- **`taxonomy.py`** — the arXiv category taxonomy (arXiv-specific paper
  enrichment). A standalone module (bundled JSON, no network); see its section
  below.

## `taxonomy.py`

### Why it exists

The arXiv category taxonomy — the ~155 arXiv codes (`cs.LG`, `math.PR`, …)
grouped into 8 top-level areas, each a `{code, name}` pair
(`cs.LG` → "Machine Learning"). Sourced once from
<https://arxiv.org/category_taxonomy> and bundled as `taxonomy.json`.

It's kept deliberately as **arXiv-specific enrichment for arXiv papers** — the
same call we made for `ar5iv`. Semantic Scholar (our paper backbone) has only
its own much coarser `fieldsOfStudy` (~20 fields), so arXiv's fine-grained
categories are something S2 can't give us. This module describes *what*
categories exist; a given paper's *own* categories come from arXiv metadata,
not S2.

### How it's structured

One tiny module over the bundled JSON — no package, no HTTP, no cache table
(unlike every other client here):

- **`_data()`** — `@lru_cache`'d parse of `taxonomy.json`, read once per
  process. Private (single-file use).
- **`groups()`** — the areas-with-categories tree, for populating a picker.
- **`valid_codes()`** — an `@lru_cache`'d `frozenset` of every code, for
  validating submitted category filters.

### Design decisions worth knowing

- **Static bundled data, not a runtime fetch.** The taxonomy changes maybe once
  a year; shipping it as a file means no network call and no cache TTL to
  reason about. That's why this module looks nothing like its HTTP-client
  neighbours.
- **No `code → name` lookup yet.** The current API answers "what areas exist"
  (`groups`) and "is this code real" (`valid_codes`), but not "what's the label
  for `cs.LG`". The planned detail-panel use (below) needs that; it'll be added
  when that feature is built, not speculatively now.
- **The docstring's old "DORMANT / no importers" claim was stale** and was
  dropped on port — `routes/search.py` imports it (traced below).

### Who uses it, and how/why (traced, not yet ported)

- **`routes/search.py`** — `GET /api/taxonomy` returns `groups()` to the
  frontend's arXiv category picker; seed search validates submitted codes
  against `valid_codes()`. **Note:** this consumer is on its way out — the
  category picker is arXiv-specific, and the search bar is migrating to
  Semantic Scholar (Phase 3), which doesn't use arXiv codes. So this *current*
  use retires with the arXiv search path.
- **Detail panel (planned, not built)** — the going-forward reason to keep this
  module: labelling an arXiv paper's own category tags (`cs.LG` →
  "Machine Learning") in the detail window, for arXiv papers only. Needs the
  `code → name` lookup above, plus the paper's categories from arXiv metadata
  (S2 doesn't carry them).

### Testing

`test_taxonomy.py` — loads the real bundled `taxonomy.json` (static data, so no
fixture or network): 8 top-level areas, a known code carries its expected label
(`cs.LG` → "Machine Learning"), `valid_codes()` covers exactly the codes in
`groups()`, and the `lru_cache` memoization returns the same object.
