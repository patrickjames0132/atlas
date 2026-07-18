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
  fields, from `semantic_scholar.vocab` — not arXiv categories, which S2 doesn't
  use).
- **`local_search`** — an instant search over the graph snapshots already in the
  SQLite cache. Purely local: it's the result you see while `live_search` is
  still in flight, and the *only* result available when S2 is rate-limiting us.
  "If you've seen a paper on a graph before, you can find it again offline."

## `live_search`, and the query-analysis seam

`live_search` strips the query, then runs three gates in order:

1. **A pasted arXiv id/URL** (`arxiv.extract_id`) resolves directly via an
   `ARXIV:<id>` lookup — no expansion (an id isn't vocabulary; an "improved"
   id could only be a wrong one), no filters (they never apply to an
   explicit lookup). An id S2 doesn't know returns nothing rather than
   falling through to a junk lexical search of the id text.
2. Otherwise the query goes through `_analyze`, and the analyst's
   **confidently recalled titles** are verified against `s2.match_title`
   (S2's `/paper/search/match`; a match failure — including an S2 error —
   skips that title, never the search). Verified papers lead the results.
   **Unless `analyst=False`** (the search bar's Options checkbox, v5.18.0):
   then this whole step is skipped — no LLM call, no recalled titles — and
   step 3 runs on the words as typed. The LLM round-trip (and its spend) is
   the user's to decline per search.
3. The **expanded query** (or the raw one, analyst off) runs through
   `s2.search_papers`, unwrapped into bare node dicts (so live and local
   search return the same shape), deduped against the verified hits, capped
   at `limit` together.

`_analyze` delegates to the **query analyst agent**
(`agents.query_analyst.analyze`). The problem it solves: S2 search is
*lexical*, so a query like "DQN" misses the seminal papers that never spell
out the acronym in their title/abstract. Expansion ("DQN" → "DQN deep
Q-network deep Q-learning") lets the search meet them halfway — and for
famous papers the analyst goes further, naming their exact titles from
parametric knowledge, which the title match verifies (an invented title
matches nothing and costs nothing beyond one lookup). The analyst
**degrades to a passthrough on any failure** (no key, network down, rate
limit), so search never breaks because the LLM hiccuped — see
`agents/query_analyst/README.md`. (Historical note: this seam spent Phase 3
as a documented passthrough precisely so the call site wouldn't move when
the agent landed — and it didn't.)

Live-search results are **cached whole for a day** (the graph-snapshot
TTL), keyed by query + filters + the analyst flag (a raw search and an
expanded search return different results, so neither may serve the other's
entry): re-typing a recent query answers instantly — no analyst call, no S2
requests. (The local snapshot search can't serve
acronym queries — "DQN" appears in no cached *title* — so repeat-query
caching is what makes the second search instant.)

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

## Who uses it, and how/why

- **`routes/search.py`** (ported) — `GET /api/search` (was `/api/arxiv_search`) calls
  `live_search`, catching `s2.S2Error` → HTTP 502; `GET /api/local_search` calls
  `local_search` and degrades to `[]` on any error (it must never block the live
  search running alongside it). The route validates a submitted fields filter
  against `semantic_scholar.vocab.valid_fields()`.

## Testing

`test_search.py` — `live_search` with the S2 calls mocked (unwrapping,
filter forwarding, blank short-circuit, the pasted-id front door, verified
titles leading + dedupe + match-failure tolerance, and that the query routes
through the `_analyze` seam), and `local_search` against the real SQLite cache on the
per-test temp DB (token matching + `has_graph`, dedupe-keeps-richer, the year
filter, and the phrase/seed/citation ranking).
