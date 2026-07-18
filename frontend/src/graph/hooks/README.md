# `src/graph/hooks`

The hooks that manage a live force simulation without fighting it.
They cluster here purely to keep `graph/` scannable (the original nesting
precedent the hybrid structure rule cites); all are consumed only by
`graph/GraphExplorer.tsx`. Everything below is shaped by the core
constraint documented in `../README.md`: react-force-graph MUTATES the
node objects, so these hooks mutate in place and signal by version, never
by identity.

```
hooks/
  useDiscovery.ts   — the sim-side discovery merge, in place
  useEscapeClear.ts — Esc = one "unhighlight everything" gesture
  useMarquee.ts     — alt-drag node selection (the teacher's scope)
  usePinning.ts     — user pins (drag / toggle / release), timeline-aware
  useTimeline.ts    — BOTH layouts' physics (the one owner of the d3 force
                      slots): Timeline's year pinning/collide/axis painting,
                      and Force's relation clustering (../clusterForce.ts)
```

## `useDiscovery` — the graph grows mid-conversation

Merges the papers a workflow pulls in (the researcher's expand/search
tools) into the live graph:

- **In-place append** with id/edge-key dedupe (an edge key is
  `source|target|type`) — the store re-feeds full discovery arrays, and the
  dedupe makes that safe.
- **Anchored spawning:** a new paper starts near the paper it was
  discovered from, so it doesn't fly in from the canvas origin when the sim
  reheats; ungrounded topic-search hits (no edge) anchor on the seed with a
  wider scatter so they settle into a loose cluster instead of stacking.
- **Year-range widening:** a discovery older/newer than anything visible
  widens both the base range and the active year filter — a discovered
  paper must never arrive invisible.
- **Reheat without camera yank:** `d3ReheatSimulation`, never `zoomToFit` —
  the user may be reading the chat, not watching the graph.
- **Changes signal by version:** the hook bumps a `graphVersion` counter
  whenever it appends to `base.nodes`/`links`, so React dependents recompute
  even though `base` is the same object. Deliberate, load-bearing, and the
  opposite of idiomatic-React immutability — RFG's ownership of the objects
  rules the immutable-copy style out.
- `discoveredNodes` mirrors what was merged, kept separately so follow-up
  questions can extend the researcher's grounding without rebuilding
  `base`; on a restored session it's re-collected from the saved nodes'
  `discovered` flags.

## `useMarquee` — hand-pick the teacher's scope

A **modifier-drag, not a mode**: hold **Alt** and drag a rectangle to pick the
nodes the AI teacher grounds in (its lectures and Q&A). The design choices that
make it coexist with the sim's own drag-to-pan:

- **Arms only while Alt is held.** A window `keydown`/`keyup` (plus a `blur`
  reset, so an alt-tab that swallows the keyup can't leave it stuck) flips an
  `armed` flag; GraphExplorer renders a transparent overlay whose
  `pointer-events` go live only then. Plain drag still reaches ForceGraph2D and
  pans — no interaction is stolen.
- **The overlay captures the drag, so RFG never sees it.** The mousedown lands
  on the arm overlay (above the canvas, below the controls in z-order), and the
  move/up run on `window` so the gesture completes even if Alt is released
  mid-drag.
- **Hit-testing is in screen space.** `fgRef.graph2ScreenCoords` maps each
  *visible* node's sim position to canvas-local pixels, compared against the
  rectangle (measured off the wrap's bounding box — the canvas fills the wrap,
  so their origins coincide). Only what's on screen is eligible, matching the
  `selected ∩ visible` grounding rule.
- **The marquee is additive.** Each alt-drag **unions** the enclosed nodes onto
  the pick, so several sweeps build one scope; a negligible drag (below a few
  pixels) is an alt-click on empty space that **clears** it, as do the
  controls' clear link and **Esc** (both of which also drop the teacher's
  highlight — see `useEscapeClear` below). We deliberately **don't** use Alt+Shift for a
  "replace vs. add" split — that combo is the OS keyboard-layout switch on
  Windows, which steals the modifier and the window focus mid-drag. Single-node
  **shift-click** add/remove lives in GraphExplorer's click handler, not here.

The selected ids live in the **workspace slice** (`selectedNodeIds`) — the one
piece of this hook's state that's genuinely cross-cutting, since
`selectGroundingNodes` reads it to scope the teacher. The rectangle and the
`armed` flag stay local (only the canvas paints them).

## `useEscapeClear` — one key drops every highlight

Highlights arrive from four owners (the teacher's beat/answer/ref glow in the
highlight slice, the hand-picked scope in the workspace slice, and their two
panel-side echoes), and each historically cleared only its own way. Esc now
runs GraphExplorer's `onClearAll` — `nodeSelectionCleared()` +
`highlightSet([])` — and the teacher panel's active beat/answer/ref marks
follow the emptied highlight on their own (`useConversation` watches the
global set, which also un-sticks the marks after a graph reload). The hook
itself is deliberately dumb: a window keydown listener that skips form
controls (Esc in the search box means "leave the box" — the Tour's
precedent); GraphExplorer additionally skips it while the lightbox or tour
own the key, since both bind their own Esc-to-close.

## `usePinning` + `useTimeline` — two layouts, one pin vocabulary

Pins are just `fx`/`fy`, but their *semantics* are layout-aware:

- **Force mode:** drag pins where dropped; unpin frees the node entirely.
- **Timeline mode:** a node's x is ALWAYS its date column — dragging only
  sets height, unpinning restores the column pin, and `releaseAll` keeps
  the date structure. `nodeTimelineX` maps year + month fraction to x, so
  papers sit *between* year gridlines by publication month (an unknown
  month means the year's own gridline; there's no day-level precision
  anywhere in this system, only year+month).
- **Undated papers are not on the Timeline at all** (v5.5.0). They used to
  sit at the **seed's own exact x**, reasoning that S2 not knowing a date
  isn't evidence a paper is old, and a citer tends to be contemporaneous
  with its seed anyway. That reasoning holds, but the rendering didn't:
  every undated paper landed on that one x, so they drew as a vertical bar
  skewered through the seed (visible on QMIX, ~12 of them). Placing a paper
  on a time axis *is* a claim about when it came out, and an undated paper
  gives us none to make — so **`GraphExplorer`'s `nodeOk` filters them out
  of the Timeline view**, while Force (where x carries no date meaning)
  still shows them. Only an undated *seed* survives the filter, since the
  seed always renders; it anchors at the earliest year. The backend also
  stopped shipping undated *citers* as Field Landmarks (a landmark is
  "top-cited citer of year Y" — a claim an undated paper can't make; see
  `services/graph/budget.py`), so in practice little reaches this filter.
- **Timeline physics:** pin every x, add a radius-sized collide force so a
  year column spreads out instead of clumping; `freezeSettledY` freezes
  heights once the sim settles so dragging one node can't re-relax the
  rest. The axis painter draws year gridlines/labels in graph coordinates,
  thinning labels when zoom would crowd them (≥28px apart on screen).
- **Force physics (v5.23.0):** the neighborhood clusters by relation —
  `applyLayoutPhysics`'s force branch registers `../clusterForce.ts`
  (sector anchors around the seed's live position, orbits growing with
  √population), a radius collide for in-cluster spacing, and stretches
  each link to its relation cluster's orbit at low strength (the default
  distance-30/leaf-strength-1 link force yanked every neighbor into one
  clump — most of the old clutter). The default link accessors are
  captured once and restored on the switch to Timeline, and the cluster
  force is removed there (sector pulls would fight the year columns).
  `useTimeline` is deliberately the ONE owner of the 'collide'/'link'/
  'cluster' force slots — a second hook writing them would fight it on
  every layout switch. A new graph re-applies whichever layout is active
  (one shared effect); discoveries re-balance the orbits for free via the
  force's own `initialize`.

## How it's verified

`tsc --noEmit` strict + oxlint. The mutation-heavy behavior (pins surviving
filters, discoveries settling near anchors, timeline freezing) is exactly
what the end-of-phase browser milestone exercises by hand.
