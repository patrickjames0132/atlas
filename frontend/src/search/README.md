# `src/search`

Finding a seed paper: the search box + its Options popover, the racing dual
search, and the pick-a-paper results panel.

```
search/
  useSeedSearch.ts — the state + logic: search options, the local/live race, flags
  Search.tsx       — the form: query box, Explore, the Options popover
  HitList.tsx      — the results panel (cache hits + live hits)
  search.css       — styles (ported light-touch)
```

## Design decisions worth knowing

- **Both searches follow the selected provider** (v5.1.0). `searchLive` and
  `searchLocal` both take the header "Data source" provider from the store, so a
  hit — and its "instant" badge — reflects the backend that would actually build
  it. `HitList`'s copy is provider-aware ("Searching **OpenAlex**…" / "From
  **OpenAlex**"), driven by `PROVIDER_LABEL[provider]` from `Atlas`.
- **The two searches race on purpose.** `searchLocal` (SQLite cache, no
  network) resolves near-instantly and renders while `searchLive` (the provider's
  live search) is still in flight — and when the provider is rate-limiting us, the
  cache is the only search there is. "Nothing matched" is an error only when BOTH
  come back empty; a live failure with local hits present degrades silently to
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
- **The field picker lazy-loads and follows the provider.** The selected
  provider's field vocabulary (`getFields(provider)` → `/api/taxonomy/<provider>`
  → `{id, name}[]`) fetches only when the popover first opens; the options are
  refetched when the provider changes. The picker shows `name` and stores the
  `id` as the filter value (S2 field name / OpenAlex numeric field id), and
  switching provider clears the now-incompatible field selection (the year window
  stays). (The old ~155-category arXiv picker died with arXiv search.)
- **The popover is "Options", not "Filters"** (v5.18.0) — it stopped being
  pure filters when it grew a behavior switch: the query-analyst checkbox.
  On by default; unticking it sends `analyst=0` so the backend skips the
  LLM expansion round-trip (and its spend) and searches the words as typed.
  The switch counts toward the button's badge like any other non-default
  option, survives a provider switch (it's provider-agnostic), and "Reset"
  puts it back on. The whole option set is one `SearchOptions` object
  (renamed from `SearchFilters` for the same reason).
- **Options never apply to a pasted id/URL** (the hint says so) — the
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
