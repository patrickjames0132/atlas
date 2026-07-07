# `src/graph`

The graph explorer's engine room: the view-model types, the visual
constants, and the three hooks that manage a live force simulation without
fighting it. (The canvas/controls/legend *components* live here too and are
documented below as they land.)

```
graph/
  model.ts          — view-model types (VNode/VLink/Base) + pure helpers
  theme.ts          — the relation color scheme + layout geometry constants
  hooks/
    useDiscovery.ts — the sim-side discovery merge, in place
    usePinning.ts   — user pins (drag / toggle / release), timeline-aware
    useTimeline.ts  — the Timeline layout: year pinning, collide, axis painting
  GraphExplorer.tsx — the composition root of the graph area (see below)
  GraphCanvas.tsx   — the ForceGraph2D wrapper: every canvas painter
  GraphControls.tsx — layout toggle, filter chips, year slider, pin/fit
  Legend.tsx        — the color legend (agent entries appear on first use)
  graph.css         — styles (ported light-touch)
```

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

(`model.ts`/`theme.ts` stay at the root: components, hooks, AND outside
consumers — `search/HitList` uses `formatPubDate`, Atlas uses `ID_RE` —
all import them. The hooks cluster under `hooks/` purely to keep the
folder scannable.)

## The components: purely presentational, by design

All three components own NO state — every set, id, and count arrives as a
prop, and every interaction fires a callback upward. That's the Phase 6
state directive in its oldest corner: the canvas paints, the shell decides.
Points worth knowing:

- **`GraphCanvas`'s ring vocabulary**: gold glow + ring = the teacher is
  talking about it; dashed ring = agent-discovered mid-chat; pale ring =
  user-pinned; bright ring = selected. Labels are zoom-gated (seed /
  selected / highlighted always; everyone else past 1.6× zoom, truncated
  at 42 chars). Influential citations draw heavier; `similar` edges get no
  arrowhead — they aren't citations, mirroring the backend's
  `influential=null` semantics.
- **It must never copy `data`** — the nodes are the live objects the sim
  mutates (the `Base` identity contract above). The lib's generic prop
  typings fight our accessor signatures, so it renders through an untyped
  alias (kept, with its comment).
- **`GraphControls`** renders the year slider only when the graph spans
  more than one year, and its hint line teaches per-layout gestures.
- **`Legend`** shows the two agent-related entries only after the agent
  has actually discovered papers — it never explains marks that aren't on
  screen.

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
  year range, counts) is built once per graph and then only ever *mutated in
  place* — rebuild it (or `.map()` it) and every position and pin evaporates,
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

## `useDiscovery` — the graph grows mid-conversation

Merges the papers a workflow pulls in (the researcher's expand/search tools, the
lecture's backward walk) into the live graph:

- **In-place append** with id/edge-key dedupe (an edge key is
  `source|target|type`).
- **Anchored spawning:** a new paper starts near the paper it was discovered
  from, so it doesn't fly in from the canvas origin when the sim reheats;
  ungrounded topic-search hits (no edge) anchor on the seed with a wider
  scatter so they settle into a loose cluster instead of stacking.
- **Year-range widening:** a discovery older/newer than anything visible
  widens both the base range and the active year filter — a discovered
  paper must never arrive invisible.
- **Reheat without camera yank:** `d3ReheatSimulation`, never `zoomToFit` —
  the user may be reading the chat, not watching the graph.
- `discoveredNodes` mirrors what was merged, kept separately so follow-up
  questions can extend the researcher's grounding without rebuilding `base`; on
  a restored session it's re-collected from the saved nodes' `discovered`
  flags.

## `usePinning` + `useTimeline` — two layouts, one pin vocabulary

Pins are just `fx`/`fy`, but their *semantics* are layout-aware:

- **Force mode:** drag pins where dropped; unpin frees the node entirely.
- **Timeline mode:** a node's x is ALWAYS its date column — dragging only
  sets height, unpinning restores the column pin, and `releaseAll` keeps the
  date structure. `nodeTimelineX` maps year + month fraction to x (papers
  sit *between* year gridlines by publication month; no-year papers get an
  "n.d." lane left of the earliest year).
- Timeline physics: pin every x, add a radius-sized collide force so a year
  column spreads out instead of clumping; `freezeSettledY` freezes heights
  once the sim settles so dragging one node can't re-relax the rest. The
  axis painter draws year gridlines/labels in graph coordinates, thinning
  labels when zoom would crowd them (≥28px apart on screen).

## `model.ts` helpers & `theme.ts`

- `primaryRel`: the one relation that colors a node — seed wins, then
  reference/citation/similar in priority order, then topic-search hits get
  their own color.
- `nodeRadius`: seed fixed-large; others scale with √citations, capped so
  megahits don't swallow the canvas.
- `formatPubDate`: parsed by hand, not `new Date` — date-only strings parse
  as UTC and can render a day off in western timezones.
- `cleanNode`: strips a live node back to persistable fields — sim x/y,
  pins, and the researcher's per-conversation `idx` all deliberately dropped.
- `ID_RE`: the client-side twin of the backend's arXiv-id regex — a pasted
  id/URL jumps straight to a graph, skipping a search round-trip. Deliberate
  duplication; the backend stays authoritative.
- `theme.ts` is the single source of visual truth (node/edge colors, dim
  states, `YEAR_SPACING`, filter labels) so the canvas painting and the DOM
  chrome can never disagree about what "a reference" looks like.

## Who uses it, and how/why (traced from the old app; components port next)

- **`GraphCanvas.tsx`** — renders `Base` through ForceGraph2D with
  `theme.ts` colors, `nodeRadius`, `drawAxis`, and the pin handlers.
- **`GraphControls.tsx`** — the layout toggle calls `applyLayoutPhysics`;
  filter chips read `REL_LABEL`/`REL_COLOR`; the year slider feeds
  `yearLo`/`yearHi`.
- **`Atlas.tsx`** (the shell, for now) — owns `base`, wires the three hooks
  together, feeds `onDiscovery` into the agent streams' handlers, and uses
  `cleanNode`/`countRels` for session save/restore.
- **`search/`** — `ID_RE` for the pasted-id fast path.

## How it's verified

`tsc --noEmit` strict + oxlint (`d3-force-3d` ships no types — its import
keeps a `@ts-expect-error`). The mutation-heavy behavior (pins surviving
filters, discoveries settling near anchors, timeline freezing) is exactly
what the end-of-phase browser milestone exercises by hand.
