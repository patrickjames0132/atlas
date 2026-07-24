# `services.graph`

Neighborhood-graph assembly — the domain core of arXiv Atlas.

```
graph/
  build.py   — build_graph: assembly logic (single-provider traversal, dedupe,
               cached); Provider + resolve_provider
  model.py   — the Pydantic Graph / Node / Edge / Seed / Counts
  budget.py  — adaptive landmark-budget serving: predict it from the seed (the
               trained model) or measure it from a pool in hand (the density rule)
  bands.py   — adaptive latest-band serving: where a seed's Latest bands start
  shape.py   — the per-request BuildShape: adaptive (the app sizes itself) vs.
               user-sized, and the cache-key suffix that keeps them apart
```

`__init__.py` re-exports `build_graph`, `Provider`, `resolve_provider`, and the
models, so callers use `graph.build_graph(...)` / `graph.Provider` without
reaching into the submodules.

## Why it exists

Everything the user sees on screen — the force-directed graph of papers around a
seed — is the output of one function, `build_graph()`. `routes/graph.py`'s
`/api/graph` endpoint is a thin HTTP wrapper over it.

Given a **seed paper** and a **provider**, it produces a Connected-Papers-style
graph: the seed at the center, surrounded by three kinds of neighbor —
references, landmark citations, and latest (recent-frontier) citations.

## One provider per graph (v5.0.0)

A graph is built from **exactly one** academic-data backend, chosen by the caller
(the header dropdown → `provider` query arg → `build_graph(provider=…)`):

- **`"s2"`** (Semantic Scholar) — seed / references / citations all via S2. Its
  live citation endpoint is newest-first with no citation sort, so landmark
  citers are recency-biased for a heavily-cited seed. `_traverse_s2` therefore
  prefers the **offline S2 citations corpus** (`s2.corpus.citation_relations`,
  citation-sorted across all history) when it's ingested and can resolve the
  seed, falling back to the recency-biased live path otherwise. Which one served
  a given build is recorded on `Graph.citation_source` (`"corpus"`/`"live"`) —
  surfaced to the UI's Field-Landmarks note.
- **`"openalex"`** — seed / references / citations all via OpenAlex, whose
  server-sorted `cites:` / `cited_by:` queries return the most-cited citers and
  references directly. Tradeoff: a famous published paper resolves to its
  lower-cited arXiv-preprint record.

This replaced the v4.x **hybrid** (S2 seed/refs/similar + OpenAlex citations,
merged with `max` counts and cross-source id dedup). A single provider means one
citation-count scale (node sizes are finally comparable across relations) and no
cross-source identity glue. The **Similar relation was retired** from the build
entirely (the S2 recommendations client lives on only for the researcher's
`expand_node`). `provider` defaults to `config.providers.default_provider` when
omitted; `resolve_provider(raw)` is the shared validator (unknown → default) used
by both the graph and search routes.

## The shape it builds

```
        references (papers the seed cites — its ancestors)
              ▲
              │  edge: seed ──▶ ancestor        (the seed is the citer)
              │
   ┌──────────┴──────────┐
   │        SEED         │
   └──────────┬──────────┘
              │
              │  edge: descendant ──▶ seed       (the descendant is the citer)
              ▼
        citations (papers that cite the seed — its descendants:
                   landmark "citation" + recent-frontier "latest")
```

`build_graph()` returns a typed **Pydantic `Graph`** (not a bare dict), with:
- **`seed`** (`Seed`) — `{arxiv_id, id, title}`, a compact summary for the header.
- **`nodes`** (`list[Node]`) — deduped papers, each the normalized node fields
  plus a `rels` list (which relations surfaced it) and an `is_seed` flag.
- **`edges`** (`list[Edge]`) — `{source, target, type, influential, rank}`;
  `type` is `reference | citation | latest` from the build (the `similar` literal
  survives on the model for researcher-discovered nodes, but the seed build never
  emits it); `influential` is S2's highly-influential flag (always `None` under
  OpenAlex); `rank` is the edge's 0-based position within its relation's order.
- **`counts`** (`Counts`) — post-dedupe edge counts per relation plus the final
  deduped node count. `counts.similar` is always `0` (kept for schema stability).
- **`citation_source`** (`"corpus"` / `"live"` / `None`) — for an s2 graph, where
  the citer relations came from (the offline corpus vs. the recency-biased live
  endpoint); `None` for OpenAlex (server-sorted, so N/A) and pre-corpus cached
  snapshots. Drives the frontend's Field-Landmarks provider note.

The models live in `model.py`, beside `build.py`'s `build_graph`. Callers that
need JSON serialize with `graph.model_dump()` — the routes hand it to `jsonify`.
The model is also what goes in and out of the cache (stored as JSON, re-validated
on read), so the shape can't silently drift — at the cost of a validate on each
cache hit, a deliberate trade.

## How it works, step by step

1. **Blank-guard, resolve provider, cache.** Empty seed → `None`. `provider`
   defaults to `config.providers.default_provider`. The cache is keyed by
   **`graph:<provider>:<seed_ref>`** — an S2 graph and an OpenAlex graph for the
   same paper are separate snapshots and must never collide. The *whole assembled
   snapshot* is cached (TTL `config.graph.cache_ttl`), so re-opening a paper is
   free. The key uses the *raw* seed reference — an arXiv id and the provider node
   id it resolves to are separate entry points on purpose, to avoid a resolution
   round-trip just to normalize the key.

2. **Resolve the seed + traverse, per provider.** `build_graph` dispatches to
   `_traverse_s2` or `_traverse_openalex`, each returning the same payload:
   `(seed_node, references, landmark_citers, latest_citers, citation_source)`, or
   `None` when the provider has no paper for the reference.
   - **S2**: an arXiv-shaped ref is looked up as `ARXIV:<id>` (S2's external-id
     syntax); a raw S2 paperId passes through untouched. `arxiv.looks_arxiv()`
     tells them apart with `ID_RE.fullmatch`. References via `s2.references`,
     citers via `s2.corpus.citation_relations` when the offline corpus can serve
     the seed, else the live `s2.citation_relations` fallback.
   - **OpenAlex**: `openalex.resolve_seed_work` accepts an arXiv id or a
     `DOI:`/`ARXIV:`/`W…` node id; references via `openalex.references`
     (`cited_by:`), citers via `openalex.citation_relations` (`cites:`), with the
     adaptive `band_start` wired in.

   This is the mechanism that lets you **re-seed on any node**, including a
   journal paper with no arXiv id, so exploration never dead-ends.

3. **Adaptive budgets** (shared by both providers). The **landmark budget always
   adapts to the seed** — there is no toggle; sizing is how the app works — by
   one of two routes to the same criterion, chosen by *what kind of pool the
   path holds*:

   - **Computed** — `budget.computed_cite_limit` runs the **STOP** rule over the
     real citer years and returns a count: the length of the citation-ranked
     prefix to ship. Used by every **whole-history** pool, injected as a
     `landmark_budget` callable: the **offline corpus** (the rule runs between
     its query's two phases, on the narrow ranking), **OpenAlex** (the rule is
     prefix-local, so its one server-sorted 200-row page holds everything the
     rule reads — `openalex._budgeted_landmarks`), and a **complete live S2
     pool** (a citer list that ends before the offset ceiling — most seeds —
     which then ships the whole corpus shape, tau-banded Latest included:
     `s2.traversal._complete_pool_relations`).
   - **Selected** — `budget.select_landmarks` walks the pool's real ranking and
     admits up to `PER_YEAR_CAP` citers **per year**, skipping years already full
     (the **SKIP** rule). Used by the live S2 fallback's **truncated** pools,
     injected as its `landmark_select` callable. A truncated pool is a recency
     sliver with no all-history ranking, and a count can only ever keep a
     **prefix** — which there is all one era (DQN's reachable pool starts 2019,
     not 2013).

   A third route — **Predicted**, an offline-trained regressor over the seed's
   age and citation count — served OpenAlex until v5.13.0, on the premise that a
   remote server-sorted query needs its `limit` *before* any citer is in hand.
   The premise fell to the STOP rule's prefix-locality (it never reads past the
   first year to overflow, and the sort puts that prefix on page one), so
   OpenAlex now computes exactly too, and the predictor has since been removed.
   See `docs/predict-vs-compute.md`'s epilogue.

     The difference between the two rules is one word — what happens when a citer
     lands on a year that's already full:

     ```
     ranked citer years:  2020  2020  2020  2019  2018  2020  2017   (cap = 2)

     STOP   third 2020 overflows  -> quit the walk       => 2, both in 2020
     SKIP   third 2020 is skipped -> carry on walking    => 5, spanning 2017-2020
     ```

     Measured on truncated DQN: STOP ships 29, all 2019–2023, with nothing from
     2024–2025 — an 18-month hole before the Latest frontier. SKIP ships 84,
     twelve in each of 2019–2025, and closes it. Both honour the same "no year
     over the cap" invariant; which is honest depends on the pool — SKIP keeps a
     truncated sliver's sparse years, while on a whole-history ranking the STOP
     prefix *is* the landmark band and tau-banded Latest closes the gap instead.
     STOP was also the retired regressor's training **label** (a regression label
     has to be a scalar) — see
     [`docs/landmark-vocabulary.md`](../../../../docs/landmark-vocabulary.md).

     Undated citers are **dropped**, not banded: a landmark is the claim
     "top-cited citer of this seed *in year Y*", which a paper with no year can't
     make — and it has no place on a time axis either. Giving them a bucket (an
     earlier cut did) ships a guaranteed `PER_YEAR_CAP` of what are mostly
     PDF-extraction stubs, all on one x, drawing a vertical bar through the seed.

   See `budget.py`'s module docstring. Both selectors carry a **config-free
   core** (`select_up_to_cap_per_year`, `computed_cite_limit`) so the exact
   serving rule can be run over simulated pools without the local
   `config.json`.

   The **latest bands adapt** too (always on, like the budget): `bands.py`
   places the band start at the **density tail edge** of the landmark cluster
   (using the fitted `bands.TAU` / `bands.MAX_SPAN`), closing the gap for an old
   seed and keeping a tight frontier for a young one, falling back to the fixed
   `caps.LATEST_NUMBER_OF_BANDS` span when the seed has too few dated landmarks.
   `build.py` injects `bands.earliest_band_year` as the OpenAlex `band_start`
   callable so `integrations` stays below `services` in the import order.

4. **Dedupe + relation accumulation.** The `add_neighbor()` closure merges
   neighbors into one node table — keyed by raw id, with identity resolved through
   the **arXiv id** whenever a sighting has one. Within a single provider this
   still earns its keep: a paper that's both a reference *and* a citer (a mutual
   citation) merges into one node carrying both rels, and OpenAlex **duplicate
   works** for one paper (two works sharing an arXiv id) collapse into one node.
   First sighting wins the slot; later ones append their tag to `rels` and fill
   fields via `_upgrade_node` (max `citation_count`, fill-if-None for summary/date
   fields). `add_neighbor` returns the **canonical id** the edge loops must use —
   for a merged paper it differs from the sighting's own id.

   A dedupe consequence for edges: two sightings can collapse onto one endpoint,
   so `add_edge()` skips self-loops and already-drawn `(source, target, type)`
   triples, and each relation's `rank` counter only advances on an edge actually
   drawn — ranks stay compact for the frontend's reveal sliders.

5. **Build typed edges — direction is load-bearing.** An edge always points from
   the citing paper to the cited one:
   - **reference** → `seed → ancestor` (the seed cites it), carries `influential`.
   - **citation** (landmark) and **latest** (recent-frontier) → `descendant →
     seed` (it cites the seed) — *opposite* direction — carry `influential`. Both
     are citers, split by recency into two relations (see the provider READMEs).

   Getting a direction backwards would silently invert the citation arrows in the
   UI, which is why this is the most-commented part of the code.

6. **Assemble + cache.** Package the `Graph` and cache its `model_dump`. Note
   `counts.nodes < references + citations` whenever dedup merged a paper that
   appeared in multiple relations.

## Design decisions worth knowing

- **The whole snapshot is cached, not the individual calls.** One cache entry per
  `(provider, seed)`, TTL'd, rather than caching each traversal separately.
  Since v6.2.0 the **build shape** joins that key — but only when it's
  non-adaptive. `BuildShape.cache_suffix()` returns `""` for an adaptive build,
  so the default path's key is byte-identical to the pre-shape one and every
  snapshot cached before shapes existed still hits; each distinct user-sized
  shape caches *beside* the adaptive snapshot instead of clobbering it. Without
  this, turning adaptive off would simply hand back the adaptive graph it was
  meant to replace.
- **Non-adaptive mode adds no branches to the traversals.** All three citation
  paths (live S2, the S2 corpus, OpenAlex) already take their sizing rules as
  *injected callables*, and already fall back to the flat
  `UNBOUNDED_LANDMARK_CAP` payload guard when a rule declines. So "ship
  everything" isn't a new code path — it's `BuildShape` injecting a budget rule
  that always returns None (and dropping the truncated-pool SKIP selector).
  `shape.py` holds that decision; no provider knows shapes exist.
- **The band-shape constants resolve at call time, not in a signature default.**
  `number_of_bands`/`nodes_per_band` default to `None` and fall back to
  `integrations.caps` inside the function. A literal default would freeze the
  constants' import-time values, so `caps` would stop being the live source of
  truth (and the traversal tests that monkeypatch it would silently pass
  against stale numbers).
- **`arxiv.looks_arxiv` uses `fullmatch`, not `search`.** (Shared with the S2
  seed lookup — it lives in `integrations.arxiv`.) We only treat a reference as an
  arXiv id when it is *entirely* one; a paperId that happens to contain id-shaped
  digits must fall through to the paperId path. (`routes/graph.py` uses
  `arxiv.ID_RE.search` instead — it's pulling an id out of pasted free text.)
- **Neighbors aren't re-hydrated.** The traversal responses carry enough for
  display, so `build_graph` never does a follow-up batch fetch. Clicking a node
  for its full detail panel is a *separate* `get_paper` call in the route (which
  stays on S2 in this phase, for both providers — OpenAlex nodes carry
  S2-resolvable ids so this works).

## Who uses it

- **`routes/graph.py`** — `GET /api/graph?seed=…&provider=…&refresh=…` calls
  `build_graph` and returns `graph.model_dump()` as JSON, catching `s2.S2Error`
  *and* `openalex.OpenAlexError` and turning either into an HTTP 502 (named for
  the active provider). The `refresh` param maps straight to the kwarg.
- **`routes/search.py`** — imports `resolve_provider` to scope the local cache
  search to the selected provider's snapshots.

## Testing

`test_graph.py` monkeypatches each provider's traversal calls with canned node
dicts and uses the real SQLite cache on the per-test temp DB. It asserts: the S2
and OpenAlex build shapes (seed + references + landmark + latest, correct edge
directions and counts, `similar` always 0); that a mutual-citation paper and an
OpenAlex duplicate-work merge into one node; that a citer that *is* the seed never
self-loops; that the cache is **keyed by provider** (S2 and OpenAlex snapshots
don't collide, and each is served from its own entry); `model_dump()` round-trips
through `Graph.model_validate`; refresh bypasses the cache; `resolve_provider`
validates/defaults; an unknown or blank seed returns `None`; and the adapted
budget is what *both* providers' citation traversals receive.

It also pins **which budget route each path gets** — since v5.11.0, **OpenAlex is
the only one predicting**. It receives the model's count because its query is
remote and server-sorted, so nothing is in hand at the moment of decision. The
corpus receives `budget.computed_cite_limit` (measure the pool you already
fetched), the live fallback `budget.select_landmarks` (band it, since a prefix of a
truncated pool strands the recent years), and both take the flat
`UNBOUNDED_LANDMARK_CAP` payload guard (`integrations/caps.py`) only as a ceiling.

The adaptive budget's own tests live in **`test_budget.py`** — the two pure rules
and the trim built on them. The latest-band serving tests are in
**`test_bands.py`**, which pins the fitted constants' contract and monkeypatches
controlled values for the behavior assertions.
