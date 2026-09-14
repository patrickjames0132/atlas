# `src/store`

The Redux store — exactly four slices, one for each piece of state found to
be *genuinely* cross-cutting (three from the Phase 6 inventory, `library`
added when the source-scope picker went stale). Everything else in
the app stays component-local, on principle: **a component's state is
defined where the component lives; only state that must be reached from
distant parts of the tree earns a slice.**

```
store/
  index.ts       — configureStore + the typed useAppDispatch/useAppSelector
  workspace.ts   — the graph, discoveries, layout + load/restore/save thunks
                   (save stores a graph *reference*; restore rebuilds)
  transcript.ts  — the reader's conversations, keyed by exploration
  highlight.ts   — the papers the teacher is currently talking about
  library.ts     — the uploaded sources (drawer writes, scope picker reads)
```

## The four slices, and who touches them

- **`transcript` holds MANY conversations, keyed by exploration.** Until
  v7.16.0 it held exactly one, and that single slot is why switching
  exploration had to *abort* whatever was streaming: a running answer would
  otherwise have carried on writing into the conversation the reader had just
  moved to. Keying it is what lets an answer keep going while you read
  something else.
  - **How a stream addresses its own conversation:** every action takes an
    optional key as its *second* argument (carried in `meta.key`); omitted, it
    targets the active one. That default is deliberate — dispatches plainly
    about what the reader is looking at (showing the lecture, clearing the
    chat) stay unkeyed and unchanged, while the streaming paths in
    `useConversation` capture their key once at stream start and pass it every
    time. Only code that can outlive a switch has to think about it.
  - **Discoveries are the one thing that cannot simply follow.** The workspace
    holds only the *active* exploration's graph, so a paper found by a
    background agent would land on a map it has nothing to do with — the exact
    cross-contamination the old abort existed to prevent. Off-screen finds go
    to that conversation's `pendingDiscoveries` and are applied when it is
    opened.
  - `running` (stream ids, not a flag: an answer and several lectures can be
    in flight together) drives the rail's still-working dots and tells the
    autosave a background conversation has settled and is worth writing.

- **`workspace`** — written by the load/restore thunks, the teacher's
  discovery dispatches, and the canvas's view-filter + node-selection
  dispatches; read by the explorer (builds `base` from `graph`, merges
  discoveries into the sim, paints the selection), the teacher (grounding =
  `(selected ∩ visible) ∪ discoveries`, via `selectGroundingNodes`; the full
  seed node via `selectSeedNode`), the legend
  (`selectHasDiscovered`/`HasSearchHits`),
  the header (seed title), and the autosave. `epoch` bumps on **Home and restore
  only** — the shell keys the teacher panel on it, so a bump remounts the
  panel and rebuilds the transcript's scroll container at the top. Since a
  conversation now survives a graph change, a graph load must not remount:
  it would throw the reader back to the start of whatever they were
  reading. In-flight streams are aborted by `useConversation` watching the
  seed change instead of by the unmount that no longer happens.
  `error` is the shared search/graph overlay surface.
  `workspaceCleared` is the Home action: workspace back to initial (epoch
  bumped so the teacher remounts), with the transcript and highlights
  clearing themselves via `extraReducers` — one dispatch, page-load state.
  It also holds **`provider`** (the header "Data source" dropdown — the
  academic-data backend every graph is built from): written by `providerSet` /
  the `switchProvider` thunk (which re-seeds the current graph), read by
  `loadGraph` (sent on every build) and `useDirectSearch` (scopes the search
  search), and persisted in a Save. Unlike the graph, it **survives Home** — an
  app-wide setting, not per-graph. `loadGraph` takes an optional `provider`
  that both builds under that backend *and* moves the dropdown to it; only a
  chat citation passes it, carrying the provider that minted the id it's
  seeding on (see `teacher/transcript/README.md`). The dropdown has to follow
  or the header would name one backend while the graph and every expand off it
  ran on another.
- **`transcript`** — written by the teacher's stream dispatches; read by the
  panel to render and by `saveWorkspace` to persist. This slice is why the
  old `onStateChange` → `teacherStateRef` plumbing died: the transcript used
  to live in Teacher.tsx with a live duplicate hoisted into Atlas purely so
  Save could read it. Reset/restore ride the workspace thunks via
  `extraReducers`, and the slice's two halves have **different owners**: a new
  graph keeps the `chat` and drops the `lectures`. The chat is the *user's* —
  they asked those questions, and loading another graph says nothing about
  being finished with the answers, so clearing it is theirs to do (the Clear
  button, or Home). Lectures belong to the *graph*: a lecture narrates the
  neighborhood you built and its beats point at that graph's nodes. Home
  (`workspaceCleared`) still empties both; a restore replaces both. This is
  only safe because citations degrade — an `[n]` whose paper is no longer
  loaded renders greyed and inert instead of silently highlighting nothing
  (`teacher/transcript/README.md`), which is why the reset used to be
  wholesale. A load seeded from a citation used to carry a `fromChat` flag
  that opened the new seed's detail panel on arrival; both flag and panel
  went in v7.11.0 (the panel covered the graph the click was waiting for), so
  a graph load now says nothing about what is selected.
  An exploration holds **one lecture** (`lecture`: its beats, or null) plus
  `lectureShown`, so hiding it doesn't throw the beats away and showing it
  again is free; `selectVisibleBeats` reads it out while shown. This was a
  per-mode cache until v7.17.0 — four slots, one per mode button, each played
  once and then toggled — which made sense while a lecture's subject was the
  button you pressed. Now the subject is the reader's scope, and by the time
  they ask again the scope has usually moved, so a second lecture is a
  different lecture rather than a revisit: `lectureStarted` replaces.
  `lectureSources` resolves the `[Sn]` library citations the beats may carry —
  one map for the lecture, not per beat, because every beat cites the same
  retrieved sources (chat turns carry their own `sourceRefs` on the message
  instead), and it is cleared on `lectureStarted` so a new lecture can't
  resolve its markers against the old one's books.
  **Restore reads three eras** (`restoredLecture` in `workspace.ts`): a current
  save's single `lecture`; a v6-era per-mode `lectures` cache, out of which it
  picks the one that was on screen (else the first played, in
  `LEGACY_MODE_ORDER`) and drops the rest; and an ancient flat `beats` array.
  Note that `lectureSources` holds **two shapes** across those eras — a marker
  index now, a map of mode → marker index then — discriminated by which
  lecture field the save carries, because renaming the field would have left
  every existing save's sources unreadable. Saves predating structured library
  citations have none; those markers degrade to raw text on restore.

  **A lecture asked for in words lives somewhere else entirely** (v7.20.0):
  its beats go on the chat turn (`chatBeatAdded` → `ChatMsg.beats`), not in
  this slot, and the turn records which assistant the router picked
  (`turnRouted` → `ChatMsg.routedTo`) so the transcript can offer the other.
  Two reducers writing to two places rather than one with a flag, because the
  slot's *replace* semantics are right for a button and wrong for a message:
  pressing Lecture twice means "show me the lecture", while sending a second
  lecture request is a second reply the reader can scroll back to. Beats on a
  turn reuse the turn's own `sourceRefs`, which chat messages already carry.
- **Two grounding scopes, differing on one question** (`scopedNodes` +
  `selectGroundingNodes` / `selectLectureNodes`): may a paper the reader cannot
  currently see be in scope? Both are the visible nodes, narrowed to
  `selected ∩ visible` when there is a hand-picked selection. They part on
  discoveries: the **researcher's** keeps every paper the agent found this
  session even when a filter hides it (it pulled the paper in deliberately, and
  an answer that forgets its own find is worse than one citing a filtered
  paper), while the **lecture's** drops it. A lecture promises to narrate *the
  papers you have on screen*, so narrating an invisible one breaks its only
  rule and the reader has no way to tell why an unfamiliar paper appeared.
  Reachable only in a narrow case — the agent finds a 2019 paper mid-chat, the
  reader filters to 2024+, then presses Lecture — which is exactly the kind of
  case that would have gone unexplained.
- **`highlight`** — the teacher writes (active beat / cited answer), the
  canvas glows. Stored as an id array (serializable); `selectHighlightSet`
  memoizes the Set the canvas wants.
- **`library`** — the uploaded sources, `loadLibrary`-thunk-fetched: the
  Sources drawer re-loads it after every upload/URL ingest/delete, and the
  teacher panel's source-scope picker reads it live (the picker used to sit
  on its own mount-time fetch, so a new upload didn't surface it until a
  page reload). The `loaded` flag lets whichever surface mounts first do
  the one initial fetch. Mirrors how the lecture-scope picker reads
  `transcript.lectures` — and like it, the *scope choices* stay
  panel-local (tracked by exclusion, so a new source is searchable by
  default); only the list itself is shared.

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
- **What deliberately stays OUT:** declutter filters, hover, the
  detail-panel selection, drawer visibility, search state, the scope
  pickers' exclusion choices, lightbox — each has one render site and lives
  there. The **hand-picked
  node selection** is the exception that proves the rule: it earns
  `workspace.selectedNodeIds` because it's genuinely cross-cutting — the
  canvas writes it (marquee / shift-click), the teacher reads it (grounding
  scope). Like `visibleNodeIds`, it's a transient exploration choice, reset
  on every load/restore and never persisted in a save.

## How it's verified

`tsc --noEmit` strict + oxlint; the save→restore round trip (transcript and
discoveries surviving) is a browser-milestone item, with the Redux devtools
action log as the debugging window.


## Two selectors that exist to keep the frontend and backend agreeing

`selectGraphEdges` (the built snapshot's edges plus anything the agent
discovered) is sent with every lecture request, because edges are what let the
backend scope a lecture to the seed's **own** neighbours — see
`agents/orchestrators/lecturer/README.md`.

`selectSatelliteCount` counts the papers that scoping will exclude, for the
sentence the lecture panel shows about them. It deliberately re-derives the
**same predicate the backend uses** (is this joined to the seed by an edge?)
rather than reusing `_origin`, the layout hint `clusterForce` computes for
orbiting satellites. Two independent notions of "satellite" is exactly how a
UI note drifts out of sync with the behaviour it describes.
