# `src/search`

Finding a seed paper: the search box + filters, the racing dual search, and
the pick-a-paper results panel.

```
search/
  useSeedSearch.ts — the state + logic: filters, the local/live race, flags
  Search.tsx       — the form: query box, Explore, the filter popover
  HitList.tsx      — the results panel (cache hits + live hits)
  search.css       — styles (ported light-touch)
```

## Design decisions worth knowing

- **The two searches race on purpose.** `searchLocal` (SQLite cache, no
  network) resolves near-instantly and renders while `searchLive` (S2) is
  still in flight — and when S2 is rate-limiting us, the cache is the only
  search there is. "Nothing matched" is an error only when BOTH come back
  empty; a live failure with local hits present degrades silently to
  cache-only mode (`liveFailed` renders a note, not an error).
- **Live hits are `GraphNode`s** — the same type as graph neighbors, so the
  meta line shows what matters across venues (date · authors · citations)
  instead of the old arXiv-only `published`/`arxiv_id` columns. Dedupe
  against local hits is by S2 `id`. When the query named a famous paper,
  the analyst's S2-verified match leads the list — no special UI, it's
  just first.
- **The year slider spans the whole corpus (1800 → now), by Patrick's
  call** — full access beats track precision. The fold-to-null trick makes
  that free: a handle parked at an endpoint reads as "no bound", so the
  default full-width slider IS the empty filter (and doesn't light the
  active-filter badge). Two overlapping `<input type=range>` elements share
  one track; the low handle z-indexes on top at the far right so it stays
  grabbable.
- **The panel appears the moment a search starts** — "Searching Semantic
  Scholar…" is immediate feedback while the analyst + S2 work, and cache
  hits render the instant they resolve, never gated on the live search.
  (Browser-milestone fix: the hidden-until-something-arrives panel made
  the analyst look like it stalled the results.)
- **Authors render reference-style** — "A & B" up to two names, "First
  et al." beyond (`refAuthors`): a hit list wants recognition, not the
  roster. The backend requests authors for search endpoints only
  (`SEARCH_FIELDS`); graph traversals stay author-less on purpose.
- **A repeated query answers instantly** — the backend caches live-search
  results whole for a day (query + filters keyed; see
  `services/search/README.md`). The local snapshot search can't serve
  acronym queries ("DQN" appears in no cached *title*), so repeat-query
  caching is what makes the second search immediate.
- **The field picker lazy-loads.** S2's ~20 fields of study fetch only when
  the popover first opens — the common no-filter path never pays it. (The
  old ~155-category arXiv picker with optgroups died with arXiv search.)
- **Filters never apply to a pasted id/URL** (the hint says so) — the
  backend resolves ids directly; the id fast path itself lives in Atlas via
  `graph/model.ts`'s `ID_RE`.

## Who uses it, and how/why (traced from the old app)

`AtlasHeader` renders `Search`; `Atlas.tsx` owns the `useSeedSearch`
instance, routes submit to graph-load (pasted id) or `runSearch` (keywords),
and renders `HitList` over the canvas — picking a hit calls the same
graph-load path as a pasted id. (Ownership may move when Atlas is split;
the seams here won't change.)

## How it's verified

`tsc --noEmit` strict + oxlint; the race behavior (instant cache hits,
degraded cache-only mode, both-empty error) is exercised in the
end-of-phase browser milestone — cut the network to see the degradation.
