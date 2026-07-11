# `src/store`

The Redux store — exactly three slices, one for each piece of state the
Phase 6 inventory found to be *genuinely* cross-cutting. Everything else in
the app stays component-local, on principle: **a component's state is
defined where the component lives; only state that must be reached from
distant parts of the tree earns a slice.**

```
store/
  index.ts       — configureStore + the typed useAppDispatch/useAppSelector
  workspace.ts   — the graph, discoveries, layout + load/restore/save thunks
  transcript.ts  — the teacher's conversation (chat + per-mode lecture cache)
  highlight.ts   — the papers the teacher is currently talking about
```

## The three slices, and who touches them

- **`workspace`** — written by the load/restore thunks and the teacher's
  discovery dispatches; read by the explorer (builds `base` from `graph`,
  merges discoveries into the sim), the teacher (grounding = graph ∪
  discoveries, via `selectGroundingNodes`; the full seed node via
  `selectSeedNode`), the legend (`selectHasDiscovered`/`HasSearchHits`),
  the header (seed title), and Save. `epoch` bumps per load/restore — the
  shell keys the teacher panel on it, replacing the old `graphKey` hack.
  `error` is the shared search/graph overlay surface.
  `workspaceCleared` is the Home action: workspace back to initial (epoch
  bumped so the teacher remounts), with the transcript and highlights
  clearing themselves via `extraReducers` — one dispatch, page-load state.
- **`transcript`** — written by the teacher's stream dispatches; read by the
  panel to render and by `saveWorkspace` to persist. This slice is why the
  old `onStateChange` → `teacherStateRef` plumbing died: the transcript used
  to live in Teacher.tsx with a live duplicate hoisted into Atlas purely so
  Save could read it. Reset/restore ride the workspace thunks via
  `extraReducers` — a fresh graph empties it, a restored session refills it.
  Lectures are held as a **per-mode cache** (`lectures`: mode → beats) plus the
  `activeMode` on screen, so each of the four modes is played once and then
  toggled show/hide for free; `selectVisibleBeats` reads out the shown mode's
  beats. Save persists the whole cache (a restore brings every played lecture
  back, not just the visible one); a pre-caching save's flat `beats` folds into
  the `history` slot on restore.
- **`highlight`** — the teacher writes (active beat / cited answer), the
  canvas glows. Stored as an id array (serializable); `selectHighlightSet`
  memoizes the Set the canvas wants.

## Design decisions worth knowing

- **Serializability draws the store boundary.** The mutable sim dataset
  (`Base`) can never live here — react-force-graph mutates its objects
  every tick, the exact opposite of what Redux state may be. The store
  holds the raw `GraphResponse` + discovery arrays (plain JSON); the
  explorer derives and owns the mutable world.
- **Save reads the store, not the canvas.** `graph.nodes ∪ discoveredNodes`
  + `graph.edges ∪ discoveredEdges` is exactly what the old code
  reconstructed from the sim-mutated objects; positions/pins were never
  persisted anyway (`cleanNode` strips the researcher's `idx` on the way out).
- **Redux Toolkit + typed hooks** (`useAppDispatch`/`useAppSelector`) —
  components never import the raw react-redux hooks. Devtools give an
  action log of every beat, token batch, and discovery: an SSE stream
  debugger for free.
- **What deliberately stays OUT:** declutter filters, hover, selection,
  drawer visibility, search state, scope picker, lightbox — each has one
  render site and lives there.

## How it's verified

`tsc --noEmit` strict + oxlint; the save→restore round trip (transcript and
discoveries surviving) is a browser-milestone item, with the Redux devtools
action log as the debugging window.
