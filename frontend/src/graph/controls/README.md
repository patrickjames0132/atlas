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
  only through them fall out of the view. The chips are driven by `REL_TYPES`
  (References / Field Landmarks / Latest Publications) — `similar` was retired
  from the seed graph in v5.0.0, so there's no Similar chip; `search`- and
  `similar`-tagged papers (both only from the researcher) have no chip and stay
  visible. (The old per-relation count sliders were retired too — the backend
  already citation-budgets each pool, so a second per-relation cap was redundant
  chrome.)
- **The citation-count slider is a dual-knob window, not a fetch.** Like the
  year range — and bounded the same way, by the graph's actual min…max
  citation counts so neither knob has dead travel — two thumbs bound a
  citation window over the already-budgeted pool. The thumbs ride a **log
  scale** (see `model.ts` `citationThreshold`) because citation counts fan out
  over orders of magnitude, and their positions map to the displayed counts.
  Full-open (min…max) shows everything; it only renders when the neighbors
  span a citation range to filter against. Reuses the `.range-dual`
  track/fill/thumb CSS.
- **The find control** (`FindBar.tsx` — a round 🔍 button pinned top-right
  of the graph area, opposite this panel, expanding into a rounded input
  pill on click) spotlights on-screen papers by title/author substring —
  purely lexical and local, no API call; the header's seed search is the
  one that fetches. It started life inside this panel (crowded), then as an
  always-open pill (read as floating in no-man's land over the Timeline
  axis) before landing on collapse-until-wanted; the bottom-right corner
  (mirroring the legend) is the agreed fallback if this doesn't stick.
  A live query pins the pill open; clearing (✕, Esc, blur while empty)
  tucks it back to the 🔍. Matching lives in `model.findMatches` over the
  *visible* view (a filtered-out paper can't match invisibly);
  GraphExplorer owns the query state and routes the matches through the
  same highlight machinery the teacher's glow uses (matches glow + label,
  everything else dims; zero hits dims the whole graph — honest feedback).
  A new graph resets it; the graph-wide Esc/clear-all drops it too.
- **The year slider only renders when the graph spans more than one
  year** — a single-year graph gets nothing to filter. Its two knobs clamp
  against each other (`lo ≤ hi`).
- **The node-selector row teaches the marquee gestures and reports the
  pick.** An always-on hint line (`alt-drag to pick nodes for the teacher ·
  shift-click to add/remove`) makes the modifier-drag discoverable — the
  gesture itself lives in `hooks/useMarquee.ts` — and once a selection OR a
  teacher highlight exists the row shows its count (`N picked`, else `N lit`)
  and a `clear` link. That link (and **Esc**, same reset — see
  `hooks/useEscapeClear.ts`) drops *everything* lit at once: the pick and the
  teacher's glow, wherever it came from. The pick scopes the
  teacher via `selectGroundingNodes` (`selected ∩ visible`), so it reads as a
  filter alongside the chips/sliders.
- **The hint line teaches per-layout gestures** — drag-to-pin in Force,
  left→right-by-year in Timeline; double-click-to-reseed in both.
- **Release** unpins every node AND reheats the simulation — it stays enabled
  with nothing pinned, because "re-settle a drifted force layout" is a want of
  its own (it used to require abusing a filter chip's reheat side effect).
  Timeline keeps its date columns through a release; only heights re-relax.
  The camera stays put: releasing no longer re-arms the one-shot zoomToFit
  latch, so the graph re-settles under the user's current zoom (Patrick's
  call — the yank out to fit-everything read as losing your place).
- **Refresh** busts the seed's day-cached snapshot server-side; the button
  disables while a load is in flight.
- **The `providerNote` line** surfaces a provider-specific caveat under the
  controls when one applies — currently the Semantic Scholar ~10k citer-offset
  limit (Field Landmarks come from the recent citer tip, not the full history).
  `GraphExplorer` passes the string (or `null`) based on the active provider.

## `Legend` — never explain marks that aren't on screen

The four relation entries (Seed / References / Field Landmarks / Latest
Publications) are static; the two agent-related entries are conditional: "Discovered by teacher" (dashed ring) appears only once the
agent has actually pulled a paper in mid-conversation, "Found by search"
(pink) only once an ungrounded topic-search hit landed. The flags come from
the workspace slice's selectors (`selectHasDiscovered` /
`selectHasSearchHits`), via `GraphExplorer`.

## How it's verified

`tsc --noEmit` strict + oxlint; slider/chip/legend behavior is a standing
item of the end-of-phase browser milestone.
