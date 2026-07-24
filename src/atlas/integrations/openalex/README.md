# `integrations.openalex`

OpenAlex is one of the app's two **standalone graph providers** (the other is
`semantic_scholar`). When the user picks **OpenAlex** in the header's provider
dropdown, this package supplies the *whole* graph for a seed: the seed resolve,
its **references**, and its **landmark + latest citer** relations — all from
OpenAlex, no cross-source mixing.

It began in v4.0.0 as the citation half of a hybrid (S2 seed/references/similar +
OpenAlex citations). **v5.0.0 retired the hybrid** for a per-graph provider
choice, so this package grew the two pieces it was missing to stand alone:
`references()` and `resolve_seed_work()` (see below). The citation logic — the
heart of why OpenAlex exists — is unchanged.

## Why it exists — the recency-bias fix

S2's citation endpoint returns citers **newest-first with no sort control** and
**stops paging at an offset of 8000**, so only the newest **9000** citers are
*reachable* at all (`REACHABLE_CITERS`). For an old or heavily-cited seed, a modest
citer limit fills entirely with this year's obscure papers before a single
famous historic citer is seen — the "landmark recency bias" (which the S2
provider still has as its interim limitation; the offline citations corpus is
the eventual fix). OpenAlex has no such ceiling. A query —

```
filter=cites:W<seed>,to_publication_date:<cutoff>&sort=cited_by_count:desc
```

— returns the **most-cited citers directly**, edge guaranteed by the `cites:`
filter (no mining, no verification), and cursor pagination has no offset ceiling.
Validated live on the Hawking 1974 seed: the top landmarks come back as Page
1976, Gibbons–Hawking 1977, Unruh 1981, Birrell–Davies 1975 — the exact early
band S2's newest-first paging buries. References work the same way, in the
outbound direction: a `cited_by:W<seed>` query returns the seed's own
bibliography, server-sorted by citation count.

### …but a *single* global sort leaves the "adolescent band" gap

Sorting the whole citer set by citation count over-corrects: it fills with old,
highly-cited papers and **starves recent citers that haven't accrued citations
yet**. Verified live — Hawking's 500th landmark had **80 citations**, a bar a
2024 paper can't clear, so recent papers fell into a visible gap between the
landmark cloud and the current frontier (the mirror image of S2's old-era bias).

So the two citer relations are:

- **Field Landmarks** (`citation`) — the **all-time most-cited** citers:
  `to_publication_date:<end of last landmark year>`, `sort=cited_by_count:desc`.
  The historic giants; naturally old. The band's *length* is **computed, not
  predicted** (since v5.13.0): `citation_relations` takes a `landmark_budget`
  callable (`services/graph` wires `budget.computed_cite_limit`, the STOP rule),
  and `_budgeted_landmarks` runs it over a **one-page probe** of the ranking —
  the rule never reads past the first year to overflow, and the server sort puts
  that prefix on page one, so the exact number costs the same single request the
  retired `cite_budget` model's prediction did. A seed whose top-200 never
  overflows pays one ceiling-sized refetch. This also guarantees no landmark
  year exceeds `PER_YEAR_CAP`, which a predicted count never could.
- **Latest Publications** (`latest`) — **recent** citers as **uniform per-year
  bands**: one `publication_year:<Y>` query per year (each top
  `LATEST_NODES_PER_BAND` = 50 by citations), from the band start **up to the
  current year** — no separate newest-date window, every recent year gets its
  own fair slice. The band's lower edge is `LATEST_NUMBER_OF_BANDS` = 5 below
  the landmark cutoff by default, but **adapts per seed** when a `band_start`
  chooser is supplied (see below): for an old seed whose landmarks tail off
  early, the bands *widen* backward to meet the cluster. The newest
  `_LATEST_YEARS` = 2 calendar years are never landmarks — they're always the top
  bands. Anything already a Field Landmark is excluded (a recent *giant* stays a
  landmark, not double-shown); the rest ship **oldest-first**, so the frontend's
  reveal slider walks forward through time toward the present.

The recent papers are deliberately **Latest Publications, not landmarks** — they
*are* recent work, and the old giants are the true field landmarks. Together the
two relations span the whole timeline with no gap (they meet/overlap where the
giants peter out). Per-year banding is the fix for a subtlety we hit live: a
single recent-window query sorted by citations lets its oldest year (longest to
accrue citations) dominate — DQN's overlay came back 214/295 for 2020/21 and only
6 for 2024. Per-year banding gives each recent year its own fair slice (a flat 50
for 2022–24). The band span's **lower edge** is itself adaptive: `citation_relations`
takes an optional `band_start` callable — `(landmark_years, landmark_max_year) →
first band year | None` — that `services/graph` wires to the trained per-seed rule
(`bands.earliest_band_year`), placing the start at the **tail edge** of the
landmark cluster (scanning back from the newest landmark year, the first year whose
count is still ≥ `tau` of the peak year's). Its return is used directly
(no only-widen clamp), so it can sit earlier than the fixed start for an old seed
(closing the gap) or later for a young one (a tight recent frontier). It's a
*parameter*, not an import, so `integrations` stays below `services` in the
dependency order; `None` (the default) keeps the fixed `number_of_bands` span.
See `services/graph/bands.py`; **tail edge**,
**band**, **landmark** and the rest of the vocabulary are defined once in
[`docs/landmark-vocabulary.md`](../../../../docs/landmark-vocabulary.md).

### Why the split is by year, not an exact date

OpenAlex dating is **coarse**: a large fraction of works carry a year-only
`publication_date` defaulted to `<year>-01-01`. A rolling 12-month *date* window
(what the S2 path used) therefore silently drops almost every recent-year citer —
verified live: DQN had **1** citer in a `from_publication_date:2025-07-09` window
but **30** in publication_year 2025 (6 of them dated exactly `2025-01-01`). So the
latest relation is built **entirely** from `publication_year:<Y>` bands (no date
window at all), each robust to the Jan-1 default by construction.

## How it's structured

```
client.py     — talks to OpenAlex over HTTP: URL+credential building, throttle,
     ↓          429/5xx retries, the OpenAlexError type
nodes.py      — translates a raw OpenAlex "work" into the app's node shape
     ↓                (id, title, abstract, year, citation count, topic tags, ...)
traversal.py  — resolve_seed_work / resolve_work (seed → work), get_paper (detail
     ↓          hydration), references (cited_by:), citation_relations/citations
     ↓          (cites:), related_works (the "similar" hop for the agent)
search.py     — search_papers: free-text relevance search (ungrounded seed discovery)
vocab.py      — the 26 top-level OpenAlex fields (id + name), for the search filter
```

Mirrors `semantic_scholar/`'s package split by concern. `__init__.py` re-exports
the public API (`OpenAlexError`, `resolve_seed_work`, `resolve_work`, `get_paper`,
`bare_work_id`, `references`, `citation_relations`, `citations`, `search_papers`,
`landmark_max_year`, `node`, `bare_openalex_id`) so callers read
`from ..integrations import openalex; openalex.references(...)`.

## Standing alone as a provider (v5.0.0 graph, v5.1.0 search + detail)

Selecting OpenAlex makes it own the *entire* provider surface:

1. **Seed resolve + hydrate** — `resolve_seed_work(seed_ref)` accepts every id
   form a seed arrives as: a bare **arXiv id** (a fresh search) or one of the
   S2-resolvable node ids an OpenAlex graph carries when the user re-seeds
   (`DOI:<doi>`, `ARXIV:<id>`, `W…`). It resolves via the free entity path for a
   `W…`/DOI, and via `resolve_work` (arXiv-DOI then title search) for an arXiv id,
   requesting `DETAIL_SELECT` so the seed carries its abstract. Its **known
   limit**, no longer masked by the hybrid: a famous *published* paper resolves
   cheapest-first through the arXiv-minted DOI to its **preprint** record, which
   is lower-cited than the canonical version. A canonical-record heuristic is
   deferred (see `docs/citation-coverage.md`).
2. **References** — `references(work_id, limit)` is a `cited_by:<work_id>` filter
   (the seed's outbound bibliography), server-sorted by `cited_by_count:desc`.
3. **Citations** — `citation_relations` / `citations`, unchanged from v4.0.0.
4. **Seed search** *(v5.1.0)* — `search_papers(query, limit, year_from, year_to,
   fields)` (in `search.py`) runs OpenAlex's `search=` relevance query over title
   + abstract + fulltext, with a year window (`from/to_publication_date`) and an
   optional field filter (`topics.field.id:fields/<id>`, OR-joined). The field
   ids come from `vocab.py` — OpenAlex's own 26 top-level fields, a *different*
   vocabulary from S2's field-of-study names (the search filter picker fetches
   the right one per provider). Used by `services/search` when OpenAlex is
   selected.
5. **Detail hydration** *(v5.1.0)* — `get_paper(ref)` fills a clicked node's
   detail panel from OpenAlex: it resolves the ref to a work (via
   `resolve_seed_work`, `DETAIL_SELECT`) and returns a node with its abstract and
   **topic tags** (`fields_of_study`, from the work's `topics`). No TL;DR
   (OpenAlex has none — the panel shows the abstract).

There is **no Similar relation** — retired from the graph build in v5.0.0, and
OpenAlex's `related_works` (concept/citation overlap, weaker than embeddings) is
a possible future addition, not built.

## Node identity — why OpenAlex nodes use S2-resolvable ids

`nodes.node()` sets each node's `id` to an S2-resolvable form, in priority order:

1. `DOI:<doi>` — nearly every landmark citer has a DOI (universal, cross-field).
2. `ARXIV:<id>` — when the work is on arXiv but has no DOI.
3. bare OpenAlex `W…` — last resort (rare).

Two reasons this id scheme still matters even though detail now hydrates via
OpenAlex:

- **Re-seed + detail resolve through it.** `get_paper`/`resolve_seed_work` resolve
  a `DOI:`/`W…` id via the free entity path (reliable) and an `ARXIV:` id via the
  arXiv-DOI path. So detail hydration and re-seeding pass the **node id** — *not*
  the bare `arxiv_id`, which can miss (a published paper's canonical OA record
  isn't aliased to the arXiv-minted DOI; the frontend's `useSelection` sends the
  node id under OpenAlex for exactly this reason).
- **Dedupe.** The shared `arxiv_id` lets `build.py` collapse an OpenAlex
  **duplicate work** (OpenAlex sometimes holds two works for one paper — verified
  live: two QMIX works) into one node.

(`arxiv_id` is filled from the work's arXiv location so arXiv links/figures still
work.) An S2-built graph is unaffected — its nodes are S2 paperIds and hydrate via
S2.

## `resolve_work` — arXiv resolution is awkward, so it tries cheapest-first

OpenAlex has **no filterable arXiv id** — it lives only inside a work's
`locations[].landing_page_url`. And the arXiv-minted DOI
(`10.48550/arXiv.<id>`) only resolves for *preprint-only* papers; a journal
version's canonical record uses the *published* DOI. So `resolve_work` does:

1. **arXiv-DOI id lookup** (`/works/doi:10.48550/arXiv.<id>`) — **free**
   (id/DOI lookups are unmetered), resolves preprint-only seeds.
2. **Title search, most-cited first** — the robust general fallback (a seed's
   own paper is overwhelmingly the top-cited title match). The title is
   sanitized first: a literal `?`/`,`/`:` in a `title.search` value returns
   HTTP 400, and the search is fuzzy anyway, so punctuation is dropped. We
   deliberately **don't** pin `publication_year` — OpenAlex's year is sometimes
   wrong (the transformer record reports 2025 for a 2017 paper), and a hard year
   filter turns that into a total resolution miss (verified live: it silently
   forced the S2 fallback for "Attention Is All You Need").

It takes a `select` argument so a seed resolve can request the heavier
`DETAIL_SELECT` (the inverted-index abstract, topics, and the primary
location — whose source display name becomes the node's `venue`) while a
neighbor uses the light `NEIGHBOR_SELECT`. Abstracts arrive as an
**inverted index** (`{word: [positions]}`); `reconstruct_abstract`
rebuilds the string.

## Pricing & throttle (verified live 2026-07-09)

OpenAlex meters usage: a free API key grants **$1/day**, the keyless `mailto`
polite pool **$0.10/day**. **Id/DOI lookups are free**; search/filter costs ~$1
per 1,000 calls. A per-seed build is a handful of filter calls, so the free tier
is ample — but `client.throttle()` still paces requests to
`config.providers.openalex.min_interval` (default 0.2s; OpenAlex allows ~10 req/s), a
separate budget/lock from the S2 client. Set `config.providers.openalex.api_key` to lift
to the $1/day pool; `mailto` is the courteous default even keyless. (OpenAlex's
generous limits are why it's the more rate-limit-resilient provider of the two.)

## Who uses it

- **`services/graph/build.py`** — `_traverse_openalex()` (selected when the graph
  is built with `provider="openalex"`) resolves the seed via `resolve_seed_work`,
  then pulls `references` + `citation_relations`. No S2 fallback — under an
  OpenAlex build, an OpenAlex failure surfaces to the route as a 502 (the graph is
  purely one provider).
- **`services/search/discovery.py`** — `_openalex_live()` (seed search under the
  OpenAlex provider) calls `search_papers`, with confidently-recalled titles
  verified via `resolve_work`.
- **`routes/graph.py`** — `/api/paper/<ref>?provider=openalex` calls `get_paper`
  to hydrate a clicked node's detail panel.
- **`agents/traversal.py`** — under an OpenAlex graph, the researcher's
  `expand_node` hops through `references` / `citations` / `related_works` (the
  `similar` hop; `related_works` is OpenAlex's concept/citation-overlap
  neighbors — weaker than S2's SPECTER2, but the closest analogue) and
  `search_papers` searches via `search_papers`. `related_works` reads the work's
  `related_works` id list, then batch-hydrates via the `openalex_id:` OR filter.

## Testing

Mirrors the source: `test_client.py` (credential params, 429/5xx backoff, the
404-as-data path), `test_nodes.py` (inverted-index abstracts, arXiv-id
extraction, id priority, topic→field-tag mapping, shape parity), `test_traversal.py`
(arXiv-DOI vs. title-search resolution; `resolve_seed_work` across the
`W…`/`DOI:`/`ARXIV:`/bare forms; `get_paper` hydration; `references` via
`cited_by:`; the two disjoint sorted citer queries, cursor paging, caps, and the
`band_start` chooser), and `test_search.py` (the `search=` relevance query, its
year-window date filter, unresolvable-work skipping). No network — HTTP is faked
at `client.request` (or `urlopen` for the client itself).
