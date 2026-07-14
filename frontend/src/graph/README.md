# `src/graph`

The graph explorer's engine room: the composition root, the view-model
types, the visual constants, and three nested sub-packages — the canvas,
the DOM chrome, and the simulation hooks — each with its own README.

```
graph/
  GraphExplorer.tsx — the composition root of the graph area (see below)
  model.ts          — view-model types (VNode/VLink/Base) + pure helpers
  theme.ts          — the relation color scheme + layout geometry constants
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
