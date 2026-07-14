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
**stops paging at a ~10k offset**. For an old or heavily-cited seed, a modest
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
  The historic giants; naturally old.
- **Latest Publications** (`latest`) — **recent** citers as **uniform per-year
  bands**: one `publication_year:<Y>` query per year (each top `latest_per_year`
  (config; default 50) by citations), from the band start **up to the current
  year** — no separate newest-date window, every recent year gets its own fair
  slice. The band's lower edge is `latest_band_years` (config; default 5) below
  the landmark cutoff by default, but **adapts per seed** when a `band_start`
  chooser is supplied (see below): for an old seed whose landmarks tail off
  early, the bands *widen* backward to meet the cluster. The newest
  `_LATEST_YEARS` = 2 calendar years are never landmarks — they're always the top
  bands. Anything already a Field Landmark is excluded (a recent *giant* stays a
  landmark, not double-shown); the rest ship **oldest-first** (a `latest_limit`
  still keeps the newest N), so the frontend's reveal slider walks forward through
  time toward the present.

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
(`bands.earliest_band_year`), placing the start at the **density tail edge** of the
landmark cluster (where the per-year count falls off). Its return is used directly
(no only-widen clamp), so it can sit earlier than the fixed start for an old seed
(closing the gap) or later for a young one (a tight recent frontier). It's a
*parameter*, not an import, so `integrations` stays below `services` in the
dependency order; `None` (the default) keeps the fixed `latest_band_years` span.
See `services/graph/bands.py` and `src/ml_pipelines/latest_gap`.

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
     ↓                (id, title, abstract, year, citation count, url, ...)
traversal.py  — resolve_seed_work / resolve_work (seed → OpenAlex work),
                references (cited_by:), citation_relations / citations (cites:)
```

Mirrors `semantic_scholar/`'s package split by concern. `__init__.py` re-exports
the public API (`OpenAlexError`, `resolve_seed_work`, `resolve_work`,
`bare_work_id`, `references`, `citation_relations`, `citations`,
`landmark_max_year`, `node`, `bare_openalex_id`) so callers read
`from ..integrations import openalex; openalex.references(...)`.

## Standing alone as a provider (v5.0.0)

The v5.0.0 provider split needed OpenAlex to own three things per graph:

1. **Seed resolve + hydrate** — `resolve_seed_work(seed_ref)` accepts every id
   form a seed arrives as: a bare **arXiv id** (a fresh search) or one of the
   S2-resolvable node ids an OpenAlex graph carries when the user re-seeds
   (`DOI:<doi>`, `ARXIV:<id>`, `W…`). It resolves via the free entity path for a
   `W…`/DOI, and via `resolve_work` (arXiv-DOI then title search) for an arXiv id,
   requesting `DETAIL_SELECT` so the seed carries its abstract. Its **known
   limit**, no longer masked by the hybrid: a famous *published* paper resolves
   cheapest-first through the arXiv-minted DOI to its **preprint** record, which
   is lower-cited than the canonical version — so an OpenAlex-built seed reads the
   preprint's count. A canonical-record heuristic is deferred (see
   `docs/citation-coverage.md`).
2. **References** — `references(work_id, limit)` is a `cited_by:<work_id>` filter
   (the seed's outbound bibliography), server-sorted by `cited_by_count:desc`. No
   local over-fetch-and-rank is needed (unlike the S2 path, whose endpoint has no
   `sort`).
3. **Citations** — `citation_relations` / `citations`, unchanged from v4.0.0
   (above).

There is **no Similar relation** — it was retired from the graph build in
v5.0.0, and OpenAlex's `related_works` (concept/citation overlap, weaker than
embeddings) is a possible future addition, not built.

## Node identity — why OpenAlex nodes use S2-resolvable ids

Even in an OpenAlex-only graph, the **detail panel still hydrates through S2** in
this phase (`/api/paper/<id>` → `s2.get_paper`), so an OpenAlex node must be
addressable by an id S2 understands. `nodes.node()` sets each node's `id` to an
S2-resolvable form, in priority order:

1. `DOI:<doi>` — nearly every landmark citer has a DOI (universal, cross-field).
2. `ARXIV:<id>` — when the work is on arXiv but has no DOI.
3. bare OpenAlex `W…` — last resort (rare; re-seed/hydration degrade for these).

So clicking an OpenAlex citer hits `/api/paper/DOI:…` → `s2.get_paper` → S2
returns the abstract *and* TL;DR OpenAlex itself can't supply. (`arxiv_id` is also
filled from the work's arXiv location so arXiv links/figures still work.) The same
id also lets `build.py` dedupe an OpenAlex **duplicate work** (OpenAlex sometimes
holds two works for one paper — verified live: two QMIX works) into a single node
via its shared arXiv id.

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
`DETAIL_SELECT` (the inverted-index abstract) while a neighbor uses the light
`NEIGHBOR_SELECT`. Abstracts arrive as an **inverted index**
(`{word: [positions]}`); `reconstruct_abstract` rebuilds the string.

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

## Testing

Mirrors the source: `test_client.py` (credential params, 429/5xx backoff, the
404-as-data path), `test_nodes.py` (inverted-index abstracts, arXiv-id
extraction, id priority, shape parity), `test_traversal.py` (arXiv-DOI vs.
title-search resolution; `resolve_seed_work` across the `W…`/`DOI:`/`ARXIV:`/bare
forms; `references` via `cited_by:`; the two disjoint sorted citer queries, cursor
paging, caps, and the `band_start` chooser widening the span vs. `None` keeping the
fixed one). No network — HTTP is faked at `client.request` (or `urlopen` for the
client itself).
