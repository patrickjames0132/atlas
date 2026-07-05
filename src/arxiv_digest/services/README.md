# `services`

Domain logic — the layer that composes the `integrations` clients and `storage`
into the app's actual features. A `services` function is what a `routes` HTTP
handler calls; the route does request parsing and error-to-status mapping, the
service does the real work.

- **`graph.py`** — assemble a paper's neighborhood graph (documented in full
  below).
- **`search.py`** — seed discovery: a live S2 search plus an instant cache-first
  search (documented below).

---

## `search.py` — seed discovery

### Why it exists

Before you can build a graph you need a seed paper. `search.py` is how you find
one, two complementary ways:

- **`live_search`** — a relevance search across all of Semantic Scholar
  (`s2.search_papers` → `/paper/search`). This replaced the app's earlier
  arXiv-only search: S2 covers 200M+ papers across venues, not just arXiv
  preprints. Optional **year** and **fields-of-study** filters (S2's own ~20
  fields, from `taxonomy.s2` — not arXiv categories, which S2 doesn't use).
- **`local_search`** — an instant search over the graph snapshots already in the
  SQLite cache. Purely local: it's the result you see while `live_search` is
  still in flight, and the *only* result available when S2 is rate-limiting us.
  "If you've seen a paper on a graph before, you can find it again offline."

### `live_search`, and the query-expansion seam

`live_search` strips the query, routes it through `_expand_query`, calls
`s2.search_papers`, and unwraps S2's `{"node": …}` into bare node dicts (so live
and local search return the same shape).

`_expand_query` is currently a **passthrough with a purpose**: it's the seam for
Claude-based query expansion, deferred to Phase 4 (it needs the LLM agent
infrastructure). The problem it will solve: S2 search is *lexical*, so a query
like "DQN" misses the seminal papers that never spell out the acronym in their
title/abstract. Expansion ("DQN" → "DQN deep Q-network deep Q-learning") is the
fix; it'll be wired to a `config.llm.agents` agent then. The seam exists now so
the call site doesn't move when that lands.

### `local_search`, step by step

1. **Tokenize** the query (lowercased whitespace split); blank → no hits.
2. **Scan every `graph:` snapshot** in the cache. For a snapshot that's still
   *fresh* (`config.graph.cache_ttl`), record its seed's ids in `fresh_seeds`
   (these are the papers whose own graph is cached — exploring them is free).
3. **Match** each node: every query token must appear (case-insensitive
   substring) in `title + authors`; apply the optional year window (a bounded
   filter excludes undatable papers).
4. **Dedupe** across snapshots by paper id, keeping the richer record — the same
   paper can be a bare neighbor in one graph and a hydrated seed (with authors)
   in another.
5. **Rank**: whole-phrase title match first, then papers explored directly as
   seeds, then citation count. Trim to `limit`.
6. **Shape** each hit as `{id, arxiv_id, title, authors, year, citation_count,
   url, has_graph}`, where `has_graph` marks the papers in `fresh_seeds`.

### Design decisions worth knowing

- **Two searches, one shape.** Both now return S2-node-shaped dicts (`live`
  unwraps S2 hits; `local` reads cached S2 nodes) — previously the arXiv-backed
  live search returned a different shape from local search.
- **Stale snapshots still match.** `local_search` matches on any cached
  snapshot, fresh or not — a paper's title doesn't expire. Freshness only
  decides `has_graph` (whether re-exploring is free).
- **No field filter on `local_search`.** Cached nodes are matched purely on
  text; the S2 fields filter is a `live_search`-only, server-side thing.

### Who uses it, and how/why (traced, not yet ported)

- **`routes/search.py`** — `GET /api/search` (was `/api/arxiv_search`) calls
  `live_search`, catching `s2.S2Error` → HTTP 502; `GET /api/local_search` calls
  `local_search` and degrades to `[]` on any error (it must never block the live
  search running alongside it). The route validates a submitted fields filter
  against `taxonomy.s2.valid_fields()`.

### Testing

`test_search.py` — `live_search` with `s2.search_papers` mocked (unwrapping,
filter forwarding, blank short-circuit, and that the query routes through the
`_expand_query` seam), and `local_search` against the real SQLite cache on the
per-test temp DB (token matching + `has_graph`, dedupe-keeps-richer, the year
filter, and the phrase/seed/citation ranking).

---

## `graph.py` — neighborhood graph assembly

### Why it exists

This is the domain core of arXiv Atlas. Everything the user sees on screen — the
force-directed graph of papers around a seed — is the output of one function,
`build_graph()`. `routes/graph.py`'s `/api/graph` endpoint is a thin HTTP
wrapper over it.

Given a **seed paper**, it produces a Connected-Papers-style graph: the seed at
the center, surrounded by three kinds of neighbor, each a different relationship
to the seed.

### The shape it builds

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

`build_graph()` returns `{"seed", "nodes", "edges", "counts"}`:
- **`seed`** — `{arxiv_id, id, title}`, a compact summary for the header.
- **`nodes`** — deduped paper dicts, each carrying a `rels` list (which
  relations surfaced it) and an `is_seed` flag.
- **`edges`** — `{source, target, type}` (+ `influential` for citation edges).
- **`counts`** — raw traversal sizes plus the final deduped node count.

### How it works, step by step

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
   the UI, which is why this is the most-commented part of the file.

6. **Assemble + cache.** Package `{seed, nodes, edges, counts}` and cache it.
   Note `counts["nodes"] < references + citations + similar` whenever dedup
   merged a paper that appeared in multiple relations.

### Design decisions worth knowing

- **The whole snapshot is cached, not the individual S2 calls.** One cache
  entry per seed, TTL'd, rather than caching each traversal separately — the
  route wants an all-or-nothing snapshot, and this keeps the cache key simple.
- **`_looks_arxiv` uses `fullmatch`, not `search`.** We only want to treat a
  reference as an arXiv id when it is *entirely* one; a random paperId that
  happens to contain id-shaped digits must fall through to the paperId path.
  (`routes/graph.py` uses `arxiv.ID_RE.search` instead — it's pulling an id out
  of pasted free text, a different job.)
- **Neighbors aren't re-hydrated.** The traversal responses carry enough for
  display, so `build_graph` never does a follow-up batch fetch. Clicking a node
  for its full detail panel is a *separate* `get_paper` call in the route.

### Who uses it, and how/why (traced, not yet ported)

- **`routes/graph.py`** — `GET /api/graph?seed=…&refresh=…` calls `build_graph`
  and returns the snapshot as JSON, catching `s2.S2Error` and turning it into an
  HTTP 502. The `refresh` query param maps straight to the `refresh` kwarg (the
  "rebuild this graph" button).

### Testing

`test_graph.py` monkeypatches the four S2 calls (`get_paper` / `references` /
`citations` / `recommendations`) with canned nodes — one of which is shared
between the references and recommendations lists — and uses the real SQLite
cache on the per-test temp DB. It asserts: the seed summary shape and that an
arXiv-shaped seed is looked up as `ARXIV:<id>` (while a raw paperId is not);
that the shared paper becomes one node with `rels == ["reference", "similar"]`;
the three edge directions exactly; the counts; the cache round-trip (second call
makes zero S2 hits) and that `refresh=True` bypasses it; and that an unknown or
blank seed returns `None`.
