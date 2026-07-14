# `src/header`

The top bar: brand, the seed-search form (composed from `search/Search` —
the search *concern* stays a root feature per the hybrid rule; the header
just renders its form), the current seed's title, the **provider dropdown**,
the three drawer toggles, and the "Powered by Claude" credit.

## Design decisions worth knowing

- **Purely presentational** — search state, the selected provider, and drawer
  visibility live in the shell/store and pass through as props.
- **The provider dropdown ("Data source") is an app-wide setting** (v5.0.0): it
  picks the academic-data backend (`Semantic Scholar` / `OpenAlex`) every graph is
  built from. Changing it dispatches `switchProvider`, which re-seeds the current
  graph under the new backend; it's disabled while a graph load is in flight.
- **The brand is the Home button** (browser-milestone addition): clicking
  "Atlas" fires `onHome`, which dispatches `workspaceCleared` — back to
  the page-load default (no graph, no results, no panel) without a reload.
- **The Assistant toggle hides until there's something to assist with** (a
  graph is open or a library exists) — no dead buttons.
- The Claude credit's starburst is inline SVG, no asset fetch.

## Who uses it / verified

Rendered once at the top of the shell. `tsc` strict + oxlint.
