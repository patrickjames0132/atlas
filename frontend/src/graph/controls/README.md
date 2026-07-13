# `src/graph/controls`

The DOM chrome over the canvas — the declutter panel and the color legend.
Two components, nested here per the hybrid structure rule: their only
parent is `graph/GraphExplorer.tsx`.

```
controls/
  GraphControls.tsx — layout toggle, per-relation filter chips, the
                      dual-knob year slider, the citation-count threshold
                      slider, count readout, release/fit/refresh actions,
                      the node-selector row (gesture hint + picked-count /
                      clear), the gesture hint line
  Legend.tsx        — the color legend (agent entries appear on first use)
```

Both are purely presentational (the Phase 6 state directive): every set,
count, and id arrives as a prop from `GraphExplorer`; every interaction
fires a callback upward. Both read `../theme.ts` (`REL_COLOR` /
`REL_LABEL` / `REL_TYPES`) so the chrome can never disagree with the
canvas about what "a reference" looks like, and both style via
`../graph.css`.

## `GraphControls` — points worth knowing

- **The relation chips are the only node-type filter.** Each toggles one
  relation on/off; a hidden relation's edges drop, and neighbors reachable
  only through them fall out of the view. (The old per-relation count
  sliders were retired — the backend already citation-budgets each pool, so
  a second per-relation cap was redundant chrome.)
- **The citation-count slider is a dual-knob window, not a fetch.** Like the
  year range — and bounded the same way, by the graph's actual min…max
  citation counts so neither knob has dead travel — two thumbs bound a
  citation window over the already-budgeted pool. The thumbs ride a **log
  scale** (see `model.ts` `citationThreshold`) because citation counts fan out
  over orders of magnitude, and their positions map to the displayed counts.
  Full-open (min…max) shows everything; it only renders when the neighbors
  span a citation range to filter against. Reuses the `.range-dual`
  track/fill/thumb CSS.
- **The year slider only renders when the graph spans more than one
  year** — a single-year graph gets nothing to filter. Its two knobs clamp
  against each other (`lo ≤ hi`).
- **The node-selector row teaches the marquee gestures and reports the
  pick.** An always-on hint line (`alt-drag to pick nodes for the teacher ·
  shift-click to add/remove`) makes the modifier-drag discoverable — the
  gesture itself lives in `hooks/useMarquee.ts` — and once a selection exists
  the row also shows the picked count and a `clear` link. The pick scopes the
  teacher via `selectGroundingNodes` (`selected ∩ visible`), so it reads as a
  filter alongside the chips/sliders.
- **The hint line teaches per-layout gestures** — drag-to-pin in Force,
  left→right-by-year in Timeline; double-click-to-reseed in both.
- **Refresh** busts the seed's day-cached snapshot server-side; the button
  disables while a load is in flight.

## `Legend` — never explain marks that aren't on screen

The five relation entries are static; the two agent-related entries are
conditional: "Discovered by teacher" (dashed ring) appears only once the
agent has actually pulled a paper in mid-conversation, "Found by search"
(pink) only once an ungrounded topic-search hit landed. The flags come from
the workspace slice's selectors (`selectHasDiscovered` /
`selectHasSearchHits`), via `GraphExplorer`.

## How it's verified

`tsc --noEmit` strict + oxlint; slider/chip/legend behavior is a standing
item of the end-of-phase browser milestone.
