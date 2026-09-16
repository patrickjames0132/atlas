# `src/graph/canvas`

The ForceGraph2D wrapper — every canvas painter for the explorer: node
fills by relation, the ring/glow vocabulary, zoom-gated labels, edge
colors/widths/arrows, and the enlarged pointer areas. One component
(`GraphCanvas.tsx`), nested here per the hybrid structure rule: its only
parent is `graph/GraphExplorer.tsx`.

## Purely presentational, by design

`GraphCanvas` owns NO state — the live node/link objects, the `fgRef`, and
every piece of interaction state (focus, pins, selection, highlights) live
in `GraphExplorer` and arrive as props; every interaction fires a callback
upward. That's the Phase 6 state directive in its oldest corner: the canvas
paints, the shell decides.

## The ring vocabulary

- **Gold glow + gold ring** — the teacher is talking about this paper
  (`highlightIds`).
- **Cyan ring** — in the teacher's scope (`selectedIds`: the alt-drag
  marquee / shift-click selection, or the papers a message asked for, which
  `send` makes the selection). While a scope is active, everything
  outside it **dims** like a focus set, so the scoped cluster stands out; the
  ring is cyan to stay distinct from the gold, pale-white, and bright-white
  rings it can coexist with.
- **Dotted outer ring** — a scoped paper the view filters would hide, drawn
  anyway (`ghostIds`, always a subset of `selectedIds`; v7.24.0). The scope
  outranks the filters, and this is what keeps "the filters are a lens"
  honest: the reader can see which papers the lens would have dropped. The
  legend names it *"In scope, hidden by your filters"* while any is drawn.
- **Dashed ring** — agent-discovered mid-chat (`node.discovered`). Drawn on
  its own path just outside the fill: stroking the fill's arc buries half the
  line width under the disc, which made the original ring easy to miss.
- **Pale ring** — user-pinned.
- **Bright ring** — the open detail-panel node (`selectedId`).

Labels are zoom-gated: seed / detail-selected / highlighted / hand-picked
always; everyone else past 1.6× zoom, truncated at 42 chars, run through
`latexToUnicode` (canvas `fillText` can't render KaTeX). Influential citations
draw heavier (1.6 vs 0.6); `similar` edges get no arrowhead — they aren't
citations, mirroring the backend's `influential=null` semantics.

## The one rule: never copy `data`

The nodes handed in are the live objects the simulation mutates
(`x`/`y`/`fx`/`fy` — see the identity contract in `../README.md`), so
nothing here may copy or recreate them. Relatedly, the lib's generic prop
typings fight our accessor signatures, so the component renders through an
untyped `ForceGraph2D` alias (kept, with its comment and lint suppression).

## Who uses it

`graph/GraphExplorer.tsx` only — it supplies the filtered `view` as `data`,
the sets/ids, and the handlers (`onNodeClick` select-vs-reseed,
`onNodeDragEnd` pinning, `onEngineStop` timeline y-freeze + one-shot
zoomToFit, `onRenderFramePre` the timeline year axis painter).

## How it's verified

`tsc --noEmit` strict + oxlint; the painting itself (rings, labels,
dimming) is exactly what the end-of-phase browser milestone eyeballs.

## Labels: why the always-on exemptions are size-capped

A node wears its title when it is the seed, the detail selection, part of a
*small* pick or highlight, or the canvas is zoomed past `LABEL_ZOOM` (1.6).

The pick/highlight exemptions exist so a deliberate selection of a few papers
stays identifiable while zoomed out — you alt-dragged three papers and want to
see which. They were unconditional until v7.17.0, and a marquee over a hundred
nodes then drew a hundred labels at every zoom level: a solid block of
overlapping white text covering the graph, including the very papers it was
meant to name. `LABEL_ALL_MAX` (12) caps both, so a large selection falls back
to the zoom gate like any other node.

The highlight half of that cap matters more than it used to: a lecture beat now
lights **every** paper it discusses, not just the handful the model listed, so a
single beat can legitimately light a dozen or more.
