# `integrations.openalex`

OpenAlex is the app's **citation backbone** — the source of a seed's *landmark*
and *latest* citer relations. It joined in v4.0.0 as the winning half of a
hybrid (see the OpenAlex spike in [`OnePager.md`](../../../../OnePager.md)):
Semantic Scholar still owns the seed resolve, references, the *Similar*
relation, and TL;DRs; OpenAlex owns citations.

## Why it exists — the recency-bias fix

S2's citation endpoint returns citers **newest-first with no sort control** and
**stops paging at a ~10k offset**. For an old or heavily-cited seed, a modest
citer limit fills entirely with this year's obscure papers before a single
famous historic citer is seen — the "landmark recency bias." S2 worked around it
with a whole `_mined_landmarks` apparatus (harvest reference lists → rank by
co-citation → verify each actually cites the seed).

OpenAlex removes the need for all of it. A query —

```
filter=cites:W<seed>,to_publication_date:<cutoff>&sort=cited_by_count:desc
```

— returns the **most-cited citers directly**, edge guaranteed by the `cites:`
filter (no mining, no verification), and cursor pagination has no offset ceiling.
Validated live on the Hawking 1974 seed: the top landmarks come back as Page
1976, Gibbons–Hawking 1977, Unruh 1981, Birrell–Davies 1975 — the exact early
band S2's newest-first paging buried.

### …but a *single* global sort leaves the "adolescent band" gap

Sorting the whole citer set by citation count over-corrects: it fills with old,
highly-cited papers and **starves recent citers that haven't accrued citations
yet**. Verified live — Hawking's 500th landmark had **80 citations**, a bar a
2024 paper can't clear, so papers from ~2022 to the latest-window cutoff fell
into a visible gap between the landmark cloud and the recent frontier (the mirror
image of S2's old-era bias).

So the two relations are:

- **Field Landmarks** (`citation`) — the **all-time most-cited** citers:
  `to_publication_date:<end of last landmark year>`, `sort=cited_by_count:desc`.
  The historic giants; naturally old.
- **Latest Publications** (`latest`) — **recent** citers: the newest date window
  (`from_publication_date:<first latest year>-01-01`, `sort=publication_date:desc`,
  the last `_LATEST_YEARS` = 2 calendar years) **plus per-year bands** below it —
  `latest_band_years` (config; default 5) separate `publication_year:<Y>` queries,
  each top `latest_per_year` (config; default 50) by citations. Anything already a
  Field Landmark is excluded (a recent *giant* stays a landmark, not double-shown);
  the rest ship **oldest-first** (a `latest_limit` still keeps the newest N), so
  the frontend's reveal slider walks forward through time toward the present.

The recent papers are deliberately **Latest Publications, not landmarks** — they
*are* recent work, and the old giants are the true field landmarks. Together the
two relations span the whole timeline with no gap (they meet/overlap where the
giants peter out). Per-year banding is the fix for a subtlety we hit live: a
single recent-window query sorted by citations lets its oldest year (longest to
accrue citations) dominate — DQN's overlay came back 214/295 for 2020/21 and only
6 for 2024. Per-year banding gives each recent year its own fair slice (a flat 50
for 2022–24). A **dynamic** window sized from the seed's age + citation count is
the natural v2 — staged in OnePager.

### Why the split is by year, not an exact date

OpenAlex dating is **coarse**: a large fraction of works carry a year-only
`publication_date` defaulted to `<year>-01-01`. A rolling 12-month *date* window
(what the S2 path used) therefore silently drops almost every recent-year citer —
verified live: DQN had **1** citer in a `from_publication_date:2025-07-09` window
but **30** in publication_year 2025 (6 of them dated exactly `2025-01-01`). So the
latest window filters from **Jan 1** of the first latest year, robust to the
Jan-1 default.

## How it's structured

```
client.py     — talks to OpenAlex over HTTP: URL+credential building, throttle,
     ↓          429/5xx retries, the OpenAlexError type
nodes.py      — translates a raw OpenAlex "work" into the app's node shape
     ↓                (id, title, abstract, year, citation count, url, ...)
traversal.py  — resolve_work (seed → OpenAlex work) + citation_relations/citations
```

Mirrors `semantic_scholar/`'s package split by concern. `__init__.py` re-exports
the public API (`OpenAlexError`, `resolve_work`, `bare_work_id`,
`citation_relations`, `citations`, `node`, `bare_openalex_id`) so callers read
`from ..integrations import openalex; openalex.citation_relations(...)`.

## Two OpenAlex-specific translations (both flagged by the spike)

### 1. Cross-source node identity — how S2 and OpenAlex nodes coexist

A citation node must be **re-seedable and hydratable through the app's existing
S2-backed paper routes** (`/api/graph`, `/api/paper/<id>`), which resolve arXiv
ids and S2's `DOI:` / `ARXIV:` id prefixes. So `nodes.node()` sets each node's
`id` to an **S2-resolvable** form, in priority order:

1. `DOI:<doi>` — nearly every landmark citer has a DOI (universal, cross-field).
2. `ARXIV:<id>` — when the work is on arXiv but has no DOI.
3. bare OpenAlex `W…` — last resort (rare; re-seed/hydration degrade for these).

The payoff falls out for free: clicking an OpenAlex citer hits
`/api/paper/DOI:…` → `s2.get_paper` → **S2 returns the abstract *and* TL;DR**
OpenAlex itself can't supply. That is the hybrid's whole point — OpenAlex
*selects* the landmark citers, S2 *enriches* them on demand. (`arxiv_id` is also
filled from the work's arXiv location so arXiv links/figures still work.)

Known limitation: an OpenAlex citer and an S2 similar/reference node for the
*same* paper carry different ids (`DOI:…` vs. S2 `paperId`), so they don't
dedupe into one graph node. In practice this is rare (a seed's ancestors and
descendants almost never overlap) — revisit by hydrating citers through S2's
batch if it ever shows.

### 2. arXiv resolution is awkward, so `resolve_work` tries cheapest-first

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

Abstracts arrive as an **inverted index** (`{word: [positions]}`);
`reconstruct_abstract` rebuilds the string. Neighbor traversals skip it
(`NEIGHBOR_SELECT`), hydrating it lazily on click via S2.

## Pricing & throttle (verified live 2026-07-09)

OpenAlex meters usage: a free API key grants **$1/day**, the keyless `mailto`
polite pool **$0.10/day**. **Id/DOI lookups are free**; search/filter costs ~$1
per 1,000 calls. A per-seed citation build is a handful of filter calls, so the
free tier is ample — but `client.throttle()` still paces requests to
`config.providers.openalex.min_interval` (default 0.2s; OpenAlex allows ~10 req/s), a
separate budget/lock from the S2 client. Set `config.providers.openalex.api_key` to lift
to the $1/day pool; `mailto` is the courteous default even keyless.

## Who uses it

- **`services/graph/build.py`** — `_citation_relations()` resolves the S2 seed
  to its OpenAlex work and pulls landmark + latest citers, **falling back to
  S2's `citation_relations`** whenever OpenAlex can't resolve the seed or the
  API errors — so the graph is never *worse* than the S2-only build, only better
  when OpenAlex succeeds.

## Testing

Mirrors the source: `test_client.py` (credential params, 429/5xx backoff, the
404-as-data path), `test_nodes.py` (inverted-index abstracts, arXiv-id
extraction, id priority, shape parity), `test_traversal.py` (arXiv-DOI vs.
title-search resolution, the two disjoint sorted citer queries, cursor paging,
caps). No network — HTTP is faked at `client.request` (or `urlopen` for the
client itself).
