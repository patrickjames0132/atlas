# `integrations.taxonomy`

The app's controlled subject vocabularies — **two**, at two granularities, one
sub-package each:

- **`arxiv`** — the ~155 fine-grained arXiv codes (`cs.LG`, `math.PR`, …)
  grouped into 8 areas, each a `{code, name}` pair. arXiv-specific.
- **`s2`** — Semantic Scholar's own much coarser ~20 fields (`Computer Science`,
  `Mathematics`, …).

## Why it exists

Two different consumers want two different vocabularies:

- The **S2 seed-search filter** needs S2's fields of study — S2's
  `/paper/search` filters on exactly these (`fieldsOfStudy`). This is the live,
  in-use vocabulary now that search runs on Semantic Scholar.
- The **detail panel** (planned) will label an arXiv paper's own category tags
  (`cs.LG` → "Machine Learning") — for arXiv papers only, the same
  arXiv-specific enrichment spirit as the `arxiv`/ar5iv package. A paper's *own*
  categories come from arXiv metadata, not S2; this package only describes
  *what* categories exist.

Keeping both here makes this the one home for "controlled subject vocabularies,"
rather than scattering them.

## How it's structured

Namespaced by source, so the two vocabularies never blur together — you call
`taxonomy.arxiv.groups()` or `taxonomy.s2.fields()`, never a flat mix. Each
source is its own **sub-package** so it can own its own data — the arXiv JSON
lives *inside* `arxiv/`, not at the shared root. The odd one out among the
integrations: static/inline data, no HTTP client, no cache.

```
arxiv/               — arXiv categories
  __init__.py          re-exports groups(), valid_codes()
  vocab.py             the query logic (loads taxonomy.json)
  taxonomy.json        the ~155 codes (arXiv-specific data, kept with its package)
s2/                  — S2 fields of study
  __init__.py          re-exports fields(), valid_fields()
  vocab.py             the inline FIELDS tuple + accessors (no data file)
```

Each sub-package's `__init__.py` is a thin shim — the descriptive docstring plus
a re-export — and the actual code lives in a `vocab.py` beside it (named the same
in both so they read alike; `vocab`, not `categories`/`fields`, so the module
never shares a name with a function it holds).

- **`arxiv/vocab.py`** — `groups()` (the areas-with-categories tree) and
  `valid_codes()` (an `@lru_cache`'d `frozenset` of every code), over a private
  `@lru_cache`'d `_data()` that parses the package's bundled `taxonomy.json`
  once.
- **`s2/vocab.py`** — `fields()` (S2's ~20 fields, alphabetical) and
  `valid_fields()`, over an inline `FIELDS` tuple. No data file — each value is
  already its own human-readable label.

`taxonomy/__init__.py` exposes the two sub-packages (`from . import arxiv, s2`);
consumers namespace through them (`taxonomy.arxiv.groups()`).

> **Naming note.** `taxonomy.arxiv` (this category list) is *not*
> `integrations.arxiv` (the ar5iv renderer + id regex). Same word, different
> full path — told apart by how you import them.

## Design decisions worth knowing

- **Namespaced, not flat.** An earlier cut re-exported `groups`/`valid_codes`/
  `fields`/`valid_fields` flat at the package root, which both blurred the two
  vocabularies and forced an awkward `all_fields()` (a bare `fields()` collided
  with the `fields` module on re-export). Splitting into `arxiv`/`s2` sub-packages
  fixes both — the source is explicit in every call, and `s2.fields()` gets its
  natural name back.
- **arXiv data is a bundled file; S2 data is inline.** 155 code+name pairs are
  worth a generated JSON; ~20 plain strings are clearer as a tuple.
- **No `code → name` lookup for arXiv yet.** The API answers "what areas exist"
  and "is this code real", not "what's the label for `cs.LG`". The planned
  detail-panel use needs that; it'll be added with that feature, not now.
- **S2 field casing is Title Case** (`"Computer Science"`), matching what S2
  returns on paper objects and accepts in the `fieldsOfStudy` filter. If it ever
  differs live, `s2.FIELDS` is the one tuple to edit.

## Who uses it, and how/why (traced)

- **`services/search.py`** (ported) — `live_search` forwards an S2 fields filter
  to `s2.search_papers` (`fieldsOfStudy`); its values come from
  `taxonomy.s2.fields()`.
- **`routes/search.py`** (not yet ported) — will serve a picker and validate a
  submitted filter against `taxonomy.s2.valid_fields()`. The arXiv
  `valid_codes()` path retires with the arXiv search bar.
- **Detail panel (planned, not built)** — `taxonomy.arxiv.groups()` / a future
  `code → name` lookup to label an arXiv paper's own category tags.

## Testing

`test_arxiv.py` — 8 arXiv areas, a known code's label (`cs.LG` →
"Machine Learning"), `valid_codes()` covers exactly the codes in `groups()`,
memoization. `test_s2.py` — the S2 vocabulary is the expected 23 fields in
alphabetical order, and `valid_fields()` rejects junk (and arXiv codes). All
offline (static/inline data).
