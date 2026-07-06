# `services.search`

Seed discovery — finding the paper you'll drop into the graph.

```
search/
  discovery.py   — live_search (S2) + local_search (cache)
```

`__init__.py` re-exports `live_search` / `local_search`, so callers use
`search.live_search(...)` directly.

## Why it exists

Before you can build a graph you need a seed paper. `search/` (in `discovery.py`)
is how you find one, two complementary ways:

- **`live_search`** — a relevance search across all of Semantic Scholar
  (`s2.search_papers` → `/paper/search`). This replaced the app's earlier
  arXiv-only search: S2 covers 200M+ papers across venues, not just arXiv
  preprints. Optional **year** and **fields-of-study** filters (S2's own ~20
  fields, from `taxonomy.s2` — not arXiv categories, which S2 doesn't use).
- **`local_search`** — an instant search over the graph snapshots already in the
  SQLite cache. Purely local: it's the result you see while `live_search` is
  still in flight, and the *only* result available when S2 is rate-limiting us.
  "If you've seen a paper on a graph before, you can find it again offline."

## `live_search`, and the query-expansion seam

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

## `local_search`, step by step

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

## Design decisions worth knowing

- **Two searches, one shape.** Both now return S2-node-shaped dicts (`live`
  unwraps S2 hits; `local` reads cached S2 nodes) — previously the arXiv-backed
  live search returned a different shape from local search.
- **Stale snapshots still match.** `local_search` matches on any cached snapshot,
  fresh or not — a paper's title doesn't expire. Freshness only decides
  `has_graph` (whether re-exploring is free).
- **No field filter on `local_search`.** Cached nodes are matched purely on text;
  the S2 fields filter is a `live_search`-only, server-side thing.

## Who uses it, and how/why (traced, not yet ported)

- **`routes/search.py`** — `GET /api/search` (was `/api/arxiv_search`) calls
  `live_search`, catching `s2.S2Error` → HTTP 502; `GET /api/local_search` calls
  `local_search` and degrades to `[]` on any error (it must never block the live
  search running alongside it). The route validates a submitted fields filter
  against `taxonomy.s2.valid_fields()`.

## Testing

`test_search.py` — `live_search` with `s2.search_papers` mocked (unwrapping,
filter forwarding, blank short-circuit, and that the query routes through the
`_expand_query` seam), and `local_search` against the real SQLite cache on the
per-test temp DB (token matching + `has_graph`, dedupe-keeps-richer, the year
filter, and the phrase/seed/citation ranking).
