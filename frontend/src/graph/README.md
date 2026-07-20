# `src/graph`

The graph explorer's engine room: the composition root, the view-model
types, the visual constants, and three nested sub-packages — the canvas,
the DOM chrome, and the simulation hooks — each with its own README.

```
graph/
  GraphExplorer.tsx — the composition root of the graph area (see below)
  model.ts          — view-model types (VNode/VLink/Base) + pure helpers
  theme.ts          — the relation color scheme + layout geometry constants
  buildShape.ts     — the user's graph-sizing preference (adaptive on/off + the
                      band shape), a localStorage-backed module store
  clusterForce.ts   — the Force layout's relation clustering (custom d3 force:
                      sector anchors around the seed, √population orbits;
                      wired by hooks/useTimeline's applyLayoutPhysics)
  graph.css         — styles for the whole graph area (ported light-touch)
  canvas/           ← sub-package: the ForceGraph2D wrapper, every canvas painter
  controls/         ← sub-package: the declutter panel + the color legend
  hooks/            ← sub-package: useDiscovery / useMarquee / usePinning / useTimeline
```

All three sub-packages are single-parent clusters under `GraphExplorer` —
the hybrid structure rule's nesting case. Their components are purely
presentational: every set, id, and count arrives as a prop, and every
interaction fires a callback upward. The canvas paints, the shell decides.

(`model.ts`/`theme.ts` stay at the root: the sub-packages AND outside
consumers — `search/HitList` uses `formatPubDate`, Atlas uses `ID_RE`,
`detail/` uses both — all import them. `graph.css` also stays at the root:
it styles the whole area, and both `controls/` components import it.)

## `GraphExplorer` — where the mutable world lives

The graph area's composition root (canvas + controls + legend + the detail
panel), moved here from the old Atlas because it's a graph concern. It owns
everything sim-side and canvas-local: the `base` dataset (derived from the
store's raw `GraphResponse`), declutter filters, hover, selection wiring,
canvas size, and the filtered `view`. From the store it reads the graph,
the discovery arrays (fed into `useDiscovery`'s in-place merge — the hook
dedupes, so re-feeding full arrays is safe), the layout, and the highlight
ids. The shell passes its overlays (hit list, loading/error/hint) as
`children`, rendered inside the canvas wrap without this component knowing
them. Note the discovery data flow is one-way: teacher → store → explorer
→ `base` — the discovery *lists* live in the workspace slice (grounding,
Save, and the legend read them there); this folder owns only the sim merge.

## The core constraint: react-force-graph MUTATES your objects

Everything in this folder is shaped by one fact. The simulation writes
`x`/`y` onto every node object each tick; pins are `fx`/`fy` fields on those
same objects; and RFG even **replaces a link's `source`/`target` ids with
node object references** once the simulation binds them. Three consequences:

- **`VNode` / `VLink` make the mutation typed.** `VNode` is a `GraphNode`
  plus the sim fields; `VLink` carries `_s`/`_t` copies of the raw endpoint
  ids, because after binding, `source`/`target` no longer *are* ids —
  filtering and persistence read `_s`/`_t`.
- **`Base` must keep object identity.** The per-graph dataset (nodes, links,
  year range, per-relation counts, the citation-count ceiling) is built once
  per graph and then only ever *mutated in place* — rebuild it (or `.map()`
  it) and every position and pin evaporates,
  because the state lives ON the objects. Filtered views derive from `Base`
  without cloning its nodes.
- **Changes signal by version, not identity.** `useDiscovery` bumps a
  `graphVersion` counter whenever it appends to `base.nodes`/`links`, so
  React dependents recompute even though `base` is the same object. This is
  deliberate, load-bearing, and the opposite of idiomatic-React immutability
  — the immutable-copy style is exactly what RFG's ownership of the objects
  rules out.

**A state-directive note (Phase 6 rule):** simulation state is inherently
canvas-local *mutable object* state — it must never move into Redux. The
store question applies to app-level state (selection, chat, filters), not
to anything in this folder.

## `model.ts` helpers & `theme.ts`

- `primaryRel`: the one relation that colors a node — seed wins, then
  reference/citation/latest in priority order (`REL_TYPES`), then topic-search
  hits get their own color, falling back to `similar` (which now only appears on
  researcher-discovered papers — the seed-graph *Similar* relation was retired in
  v5.0.0).
- `nodeRadius`: seed fixed-large; others scale with √citations, capped so
  megahits don't swallow the canvas.
- `citationThreshold`: maps a citation-slider knob position to its citation
  count on a log scale spanning the graph's min…max (`log1p`/`expm1` anchor
  the ends), so the filter's travel matches how citation counts actually fan
  out and neither knob idles outside the real range.
- `formatPubDate`: parsed by hand, not `new Date` — date-only strings parse
  as UTC and can render a day off in western timezones.
- `cleanNode`: strips a live node back to persistable fields — sim x/y,
  pins, and the researcher's per-conversation `idx` all deliberately dropped.
- `ID_RE`: the client-side twin of the backend's arXiv-id regex — a pasted
  id/URL jumps straight to a graph, skipping a search round-trip. Deliberate
  duplication; the backend stays authoritative.
- `theme.ts` is the single source of visual truth (node/edge colors, dim
  states, `YEAR_SPACING`, filter labels) so the canvas painting and the DOM
  chrome can never disagree about what "a reference" looks like. `REL_COLOR`
  drives the graph, chips, legend, and lecture buttons; `BADGE_COLOR` /
  `BADGE_LABEL` drive the detail-panel badges, where both citing relations
  (`citation` and `latest`) read as one "citation" badge in a lighter green
  (the graph's landmark green was darkened to separate it from `latest`, so the
  badge keeps the original in-between shade).

## `buildShape.ts` — how much graph the backend ships

A module-level store behind `useSyncExternalStore`, the same pattern as
`ui/theme.ts` and for the same reason: the settings modal writes it,
`GraphControls` reads it to decide whether the count sliders exist, and
`api/graph.ts` reads it *outside React* to put it on the request.

- **`adaptive` is the headline.** ON (the default) the backend sizes the graph
  itself — the STOP/SKIP rules pick the landmark band, the fitted tau rule
  places the Latest cluster start — and the other three fields are inert. OFF,
  the build ships everything up to the payload guard and the user sizes the
  bands (`clusterStart`, `numberOfBands`, `nodesPerBand`).
- **It's browser state, not config.** Every other knob lives in `config.json`;
  this one belongs to the person exploring and changes between one build and
  the next, so it rides along as query parameters. The v6.0.0 purge deleted the
  old file toggles deliberately and this doesn't bring them back.
- **It's not a Redux slice either.** `workspace.provider` is the closest
  analogue, but that's part of a *saved session* — reopening a saved graph
  should rebuild it the way *you* currently size graphs, not the way whoever
  saved it did. localStorage, like the theme, is the honest home.
- **`shapeParams` sends nothing while adaptive**, so the common request URL is
  exactly what it was before shapes existed. `sameBuild` likewise treats any
  two adaptive shapes as equal — that's what stops Atlas rebuilding the graph
  on modal close when nothing that matters changed.

## The per-chip count sliders

With adaptive OFF, each relation chip in `GraphControls` grows a count slider,
and `GraphExplorer` trims the view by it. Worth knowing:

- **They're a display trim, not a rebuild.** Widening one back costs nothing —
  the papers were already shipped. Only the *build shape* triggers a refetch:
  the `adaptive` switch immediately, the band-shape numbers on modal close.
- **The chip is the slider's label.** With automatic sizing off, `GraphControls`
  drops the wrapping pill row and instead renders each relation as its filter
  chip sitting atop its own count slider (`rel-cap-group`). The chip is the same
  toggle it always was — click to hide/show the relation, highlighted while on —
  it just now heads a slider. A slider appears only under a chip that's on and
  holds more than one paper; an off or single-paper relation shows the chip
  alone. The whole block keeps `data-tour="relations"`, and the tour's "How many
  of each" step gates on a `.rel-cap-slider` existing.
- **Ranking is computed over `base`, not the filtered view**, so dragging the
  year slider doesn't silently renumber what "top 20 landmarks" means.
- **A node survives if it ranks inside the cap of at least one of its enabled
  relations** — mirroring the reachability rule, so a paper that's both a top
  reference and a mid-ranked landmark keeps the slot its best relation earns.
- **A full-span slider deletes the cap** rather than storing the total, so a
  later discovery widening the relation isn't clipped to yesterday's count.

## Who uses it, and how/why

- **`Atlas.tsx`** (the shell) — renders `GraphExplorer` and passes its
  overlays as children; uses `ID_RE` for the pasted-id fast path.
- **`detail/`** — `useSelection` types against `Base`/`VNode`;
  `DetailPanel` uses `formatPubDate` + `BADGE_COLOR`.
- **`search/HitList`** — `formatPubDate`.
- **`store/workspace`** — `cleanNode`/`countRels` for session save/restore.

## How it's verified

`tsc --noEmit` strict + oxlint (`d3-force-3d` ships no types — its import
keeps a `@ts-expect-error`). The mutation-heavy behavior (pins surviving
filters, discoveries settling near anchors, timeline freezing) is exactly
what the end-of-phase browser milestone exercises by hand.
