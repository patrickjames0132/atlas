# `services.graph`

Neighborhood-graph assembly — the domain core of arXiv Atlas.

```
graph/
  build.py   — build_graph: the assembly logic (S2 traversals, dedupe, cached)
  model.py   — the Pydantic Graph / Node / Edge / Seed / Counts
```

`__init__.py` re-exports `build_graph` and the models, so callers use
`graph.build_graph(...)` / `graph.Graph` without reaching into the submodules.

## Why it exists

Everything the user sees on screen — the force-directed graph of papers around a
seed — is the output of one function, `build_graph()`. `routes/graph.py`'s
`/api/graph` endpoint is a thin HTTP wrapper over it.

Given a **seed paper**, it produces a Connected-Papers-style graph: the seed at
the center, surrounded by three kinds of neighbor, each a different relationship
to the seed.

## The shape it builds

```
        references (papers the seed cites — its ancestors)
              ▲
              │  edge: seed ──▶ ancestor        (the seed is the citer)
              │
   ┌──────────┴──────────┐
   │        SEED         │──▶ similar neighbor   (embedding-similar; no direction meaning)
   └──────────┬──────────┘
              │
              │  edge: descendant ──▶ seed       (the descendant is the citer)
              ▼
        citations (papers that cite the seed — its descendants)
```

`build_graph()` returns a typed **Pydantic `Graph`** (not a bare dict), with:
- **`seed`** (`Seed`) — `{arxiv_id, id, title}`, a compact summary for the header.
- **`nodes`** (`list[Node]`) — deduped papers, each the normalized S2 node fields
  plus a `rels` list (which relations surfaced it) and an `is_seed` flag.
- **`edges`** (`list[Edge]`) — `{source, target, type, influential}`;
  `influential` is `None` on `similar` edges (it's a citation-only flag).
- **`counts`** (`Counts`) — raw traversal sizes plus the final deduped node count.

The models live in `model.py`, beside `build.py`'s `build_graph`. Callers that
need JSON serialize with `graph.model_dump()` / `graph.model_dump_json()` — the
routes hand `model_dump()` to `jsonify`. The model is also what goes in and out
of the cache (stored as JSON, re-validated on read), so the shape can't silently
drift — at the cost of a validate on each cache hit, a deliberate trade.

## How it works, step by step

1. **Blank-guard + cache.** Empty seed → `None`. Otherwise check the cache under
   `graph:<seed_ref>`. The *whole assembled snapshot* is cached (TTL
   `config.graph.cache_ttl`), so re-opening a paper is free and doesn't re-hit
   the rate-limited S2 API. The key is the *raw* seed reference — an arXiv id and
   the S2 paperId it resolves to are cached as separate entry points on purpose,
   to avoid a resolution round-trip just to normalize the key.

2. **Resolve the seed.** The seed reference can be two different things, and S2
   addresses them differently:
   - an **arXiv id** (from the search box) → looked up as `ARXIV:<id>` (S2's
     external-id syntax),
   - a raw **S2 paperId** (from clicking a node in an existing graph) → passed
     through untouched.

   `_looks_arxiv()` tells them apart with `arxiv.ID_RE.fullmatch` (whole-string
   match — a bare paperId must not be mistaken for an id). This is the mechanism
   that lets you **re-seed on any node**, including a journal paper with no arXiv
   id, so exploration never dead-ends. If S2 has no paper → `None`.

3. **One detail call + three traversals.** `get_paper` (already done, for the
   seed) then `references`, `citations`, `recommendations` — each capped by its
   own `config.graph.*_limit`. Neighbors come back already hydrated with light
   display fields, so no extra batch call is needed.

4. **Dedupe with relation accumulation.** The `add_neighbor()` closure merges
   neighbors into one node table keyed by paperId. The same paper can surface
   through more than one relation (both a reference *and* a recommendation);
   first sighting wins for the node body, and every later sighting just appends
   its tag to that node's `rels` — so one paper reached three ways is one node
   with three tags, not three nodes.

5. **Build typed edges — direction is load-bearing.** An edge always points
   from the citing paper to the cited one:
   - **reference** → `seed → ancestor` (the seed cites it), carries `influential`
   - **citation** → `descendant → seed` (it cites the seed) — *opposite*
     direction — carries `influential`
   - **similar** → `seed → neighbor` — recommendations aren't citations, so
     there's no citation direction and no `influential`; the edge just anchors
     the neighbor to the seed visually.

   Getting a direction backwards would silently invert the citation arrows in
   the UI, which is why this is the most-commented part of the code.

6. **Assemble + cache.** Package the `Graph` and cache its `model_dump`. Note
   `counts.nodes < references + citations + similar` whenever dedup merged a
   paper that appeared in multiple relations.

## Design decisions worth knowing

- **The whole snapshot is cached, not the individual S2 calls.** One cache entry
  per seed, TTL'd, rather than caching each traversal separately — the route
  wants an all-or-nothing snapshot, and this keeps the cache key simple.
- **`_looks_arxiv` uses `fullmatch`, not `search`.** We only want to treat a
  reference as an arXiv id when it is *entirely* one; a random paperId that
  happens to contain id-shaped digits must fall through to the paperId path.
  (`routes/graph.py` uses `arxiv.ID_RE.search` instead — it's pulling an id out
  of pasted free text, a different job.)
- **Neighbors aren't re-hydrated.** The traversal responses carry enough for
  display, so `build_graph` never does a follow-up batch fetch. Clicking a node
  for its full detail panel is a *separate* `get_paper` call in the route.

## Who uses it, and how/why (traced, not yet ported)

- **`routes/graph.py`** — `GET /api/graph?seed=…&refresh=…` calls `build_graph`
  and returns `graph.model_dump()` as JSON, catching `s2.S2Error` and turning it
  into an HTTP 502. The `refresh` query param maps straight to the `refresh`
  kwarg (the "rebuild this graph" button).

## Testing

`test_graph.py` monkeypatches the four S2 calls (`get_paper` / `references` /
`citations` / `recommendations`) with canned node dicts — one shared between the
references and recommendations lists — and uses the real SQLite cache on the
per-test temp DB. It asserts: the typed `Seed`/`Edge`/`Counts` values and that an
arXiv-shaped seed is looked up as `ARXIV:<id>` (a raw paperId is not); that the
shared paper becomes one `Node` with `rels == ["reference", "similar"]`; the
three edge directions exactly; that `model_dump()` round-trips through
`Graph.model_validate` (the cache-hit path); the cache round-trip (second call
makes zero S2 hits) and that `refresh=True` bypasses it; and that an unknown or
blank seed returns `None`.
