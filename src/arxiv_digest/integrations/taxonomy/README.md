# `integrations.taxonomy`

The full arXiv category taxonomy — arXiv-specific enrichment for arXiv papers.

## Why it exists

The ~155 arXiv category codes (`cs.LG`, `math.PR`, …) grouped into 8 top-level
areas, each a `{code, name}` pair (`cs.LG` → "Machine Learning"). Sourced once
from <https://arxiv.org/category_taxonomy> and bundled as `taxonomy.json`.

It's kept deliberately as **arXiv-specific enrichment for arXiv papers** — the
same call we made for `ar5iv`. Semantic Scholar (our paper backbone) carries
only its own much coarser `fieldsOfStudy` (~20 fields), so arXiv's fine-grained
categories are something S2 can't give us. This package describes *what*
categories exist; a given paper's *own* categories come from arXiv metadata,
not S2.

## How it's structured

The odd one out among the integrations — static bundled data, so no HTTP client
and no cache table. Still split into a package the same transport-vs-domain way
as its neighbours, so they all read alike:

```
loader.py     — loads + memoizes the bundled taxonomy.json (data access)
     ↓
categories.py — the query API: groups(), valid_codes()
```

- **`loader.py`** — `data()`, an `@lru_cache`'d parse of the bundled
  `taxonomy.json` (read once per process). Public within the package because
  `categories` queries it across the module boundary — the file-load analogue
  of the HTTP packages' `client.fetch_*`.
- **`categories.py`** — `groups()` (the areas-with-categories tree, for
  populating a picker or labelling a paper's tags) and `valid_codes()` (an
  `@lru_cache`'d `frozenset` of every code, for validating submitted filters).

`__init__.py` re-exports `groups` and `valid_codes`.

## Design decisions worth knowing

- **Static bundled data, not a runtime fetch.** The taxonomy changes maybe once
  a year; shipping it as a file means no network call and no cache TTL to
  reason about. That's why this package has a `loader` where its neighbours
  have a `client`.
- **No `code → name` lookup yet.** The API answers "what areas exist"
  (`groups`) and "is this code real" (`valid_codes`), but not "what's the label
  for `cs.LG`". The planned detail-panel use (below) needs that; it'll be added
  when that feature is built, not speculatively now.
- **The original module's "DORMANT / no importers" docstring was stale** and
  was dropped on port — `routes/search.py` imports it (traced below).

## Who uses it, and how/why (traced, not yet ported)

- **`routes/search.py`** — `GET /api/taxonomy` returns `groups()` to the
  frontend's arXiv category picker; seed search validates submitted codes
  against `valid_codes()`. **Note:** this consumer is on its way out — the
  category picker is arXiv-specific, and the search bar is migrating to
  Semantic Scholar (Phase 3), which doesn't use arXiv codes. So this *current*
  use retires with the arXiv search path.
- **Detail panel (planned, not built)** — the going-forward reason to keep this
  package: labelling an arXiv paper's own category tags (`cs.LG` →
  "Machine Learning") in the detail window, for arXiv papers only. Needs the
  `code → name` lookup above, plus the paper's categories from arXiv metadata
  (S2 doesn't carry them).

## Testing

`test_loader.py` — `data()` returns the parsed document and is memoized.
`test_categories.py` — 8 top-level areas, a known code carries its expected
label (`cs.LG` → "Machine Learning"), `valid_codes()` covers exactly the codes
in `groups()`, and the `lru_cache` returns the same object. All against the real
bundled `taxonomy.json` (static data, so no fixture or network).
