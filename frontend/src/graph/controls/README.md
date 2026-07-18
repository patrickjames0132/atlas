# `src/graph/controls`

The DOM chrome over the canvas — the declutter panel and the color legend.
Two components, nested here per the hybrid structure rule: their only
parent is `graph/GraphExplorer.tsx`.

```
controls/
  GraphControls.tsx — a collapsible header bar over: layout toggle,
                      per-relation filter chips, the dual-knob year slider,
                      the citation-count threshold slider, the count
                      readout + release/fit/refresh/clear action row, the
                      node-selector gesture hint, the per-layout hint line
  Legend.tsx        — the color legend (agent entries appear on first use)
```

Both are purely presentational (the Phase 6 state directive): every set,
count, and id arrives as a prop from `GraphExplorer`; every interaction
fires a callback upward. Both read `../theme.ts` (`REL_COLOR` /
`REL_LABEL` / `REL_TYPES`) so the chrome can never disagree with the
canvas about what "a reference" looks like, and both style via
`../graph.css`.

## `GraphControls` — points worth knowing

- **The whole panel collapses to its header bar.** The "Graph controls"
  header is a button: clicking it hides the body and shrinks the panel to a
  slim strip (the find control's collapse-until-wanted idea, panel-sized),
  giving the canvas the 272px box back; the count readout rides the
  collapsed bar so the panel still reports its state while tucked away. The collapsed flag
  is the panel's one piece of local state (like FindBar's own open/closed).
  The body hides via `hidden`, **not** unmounting — the guided tour judges
  its year/citation stops by element *existence* (`presentIf`), and those
  targets must survive a collapse. The panel steps stage `'controls'`
  (`tour/steps.ts` → `Atlas` → `GraphExplorer`'s `tourStage` → the
  `stagedOpen` prop), which re-expands a collapsed panel so the walk has
  something to spotlight; it never re-collapses after (no tidy-up, same as
  the detail panel's staged seed selection).
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
- **The find control** (`FindBar.tsx` — a round 🔍 button pinned bottom-right
  of the graph area, mirroring the legend, expanding into a rounded input
  pill on click) spotlights on-screen papers by title/author substring —
  purely lexical and local, no API call; the header's seed search is the
  one that fetches. It started life inside this panel (crowded), then as an
  always-open pill (read as floating in no-man's land over the Timeline
  axis), then collapse-until-wanted pinned top-right, before moving to the
  bottom-right corner (the fallback agreed when top-right shipped).
  A live query pins the pill open; clearing (✕, Esc, blur while empty)
  tucks it back to the 🔍. When there are hits, a **"select" link — or
  Enter in the box — commits the whole match set to the teacher's
  hand-picked scope** in one press (both affordances on purpose: the link
  is discoverable, Enter is fast) — additive via `nodeSelectionAdded`,
  exactly like the marquee — and GraphExplorer clears the find so the
  cyan selection (not the find spotlight) shows the result: find →
  select → ask in three gestures.
  Matching lives in `model.findMatches` over the
  *visible* view (a filtered-out paper can't match invisibly);
  GraphExplorer owns the query state and routes the matches through the
  same highlight machinery the teacher's glow uses (matches glow + label,
  everything else dims; zero hits dims the whole graph — honest feedback).
  A new graph resets it; the graph-wide Esc/clear-all drops it too.
- **The year slider only renders when the graph spans more than one
  year** — a single-year graph gets nothing to filter. Its two knobs clamp
  against each other (`lo ≤ hi`).
- **One count readout, shared by the footer and the collapsed bar.** The
  same string renders in both places: `N / total papers shown` under bare
  filters, flipping to `N / shown papers selected` while a hand-pick exists —
  out of the *shown* papers, not the total, since the pick scopes the teacher
  as `selected ∩ visible` (`selectGroundingNodes`). The old `N picked · clear`
  status row under the gesture hint retired in favor of this flip.
- **The node-selector row teaches the marquee gestures.** An always-on hint
  line (`alt-drag to pick nodes for the teacher · shift-click to add/remove`)
  makes the modifier-drag discoverable — the gesture itself lives in
  `hooks/useMarquee.ts`. Clearing the pick moved into the action row: the
  **Clear** button (disabled until a pick or a teacher highlight exists — and
  **Esc**, same reset, see `hooks/useEscapeClear.ts`) drops *everything* lit
  at once: the pick and the teacher's glow, wherever it came from.
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
