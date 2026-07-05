# `services`

Domain logic — the layer that composes the `integrations` clients and `storage`
into the app's actual features. A `services` function is what a `routes` HTTP
handler calls; the route does request parsing and error-to-status mapping, the
service does the real work.

- **`graph.py`** — assemble a paper's neighborhood graph (documented in full
  below).
- **`search.py`** — seed discovery. **Not yet ported**; being rebuilt on
  Semantic Scholar (replacing the arXiv-search path) with Claude-based query
  expansion. This README gets a `search` section when that lands.

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
