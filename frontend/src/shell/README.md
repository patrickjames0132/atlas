# `src/shell`

The app's frame: the collapsible left rail, and the shell-level state that
decides what fills the main pane.

```
shell/
  SideBar.tsx    — the rail: brand + seed, New Exploration, explorations,
                   Library, Settings, theme, tour, and the data-source picker
  useSessions.ts — the exploration list and its CRUD
  useAutosave.ts — the autosave: debounce, commit points, once-per-row titling
  shell.css      — the rail and its menus
```

## Why the header became a rail (v7.8.0)

A top bar spends the scarcest axis — vertical — on chrome that is mostly idle,
and it can't be put away. A rail spends the plentiful one and folds to 56px
when the map wants the room. It's the shape ChatGPT and Claude both settled
on, and this is a deliberate copy of it rather than a variation.

The move also let the **explorations** stop hiding behind a drawer button. A
thing you accumulate should be visible; that band is what made the rail worth
building, and the Sessions drawer retired into it.

## Design decisions worth knowing

- **Three bands, one scroller.** Top (collapse toggle + brand + seed title +
  New Exploration) and bottom (data source, Library, Settings, theme, tour)
  are fixed; only the exploration list scrolls, so both fixed bands stay
  reachable however many have piled up.
- **Collapsed is *actions only*.** The saved list and the labelled data-source
  select are expanded-only. A column of identical 🗂 glyphs distinguishes
  nothing, and titles are the entire point of that list; likewise a bare
  cylinder can't show *which* source is selected, which is the only thing that
  control has to say at a glance. Collapsed, the data source becomes an icon
  with a popup — one click selects and closes, unlike the chat bar's
  multi-select source picker, which has to stay open while you tick things.
- **The seed title sits beside the brand.** It spent two builds on the canvas
  — first top-left over the graph controls, then centred over the map — and
  every placement collided with something at some panel width. In the rail it
  truncates instead of colliding, next to the other thing that answers "where
  am I". Only the labels are controls-adjacent; the brand row is a plain
  `.rail-item` like every entry below it, so its glyph lands on the same 18px
  centre line and its hover highlight spans the rail (v7.11.0 — a highlight
  that stopped at the glyph made the row read as an icon button with two
  words parked beside it). The whole row toggles the rail; the seed keeps its
  own tooltip inside the button's, because it is the one thing here that
  truncates.
- **The rail resizes like the other panels** (`useResizablePanel`, 180–380px,
  persisted). The hook gained a `side` option rather than a twin: a
  left-docked panel is the exact mirror of a right-docked one, so only the
  sign of the drag differs. Width applies while expanded only — a 300px-wide
  strip of icons would be absurd.
- **The handle folds the rail both ways** (v7.11.0, the Azure DevOps
  gesture). Drag past the 180px floor to `closeAt: 130` and it folds; the
  folded rail *keeps its handle*, and a drag back past `openAt: 96` (40px out
  from the 56px icon rail) opens it again — a collapsed edge you couldn't grab
  would make the collapse a one-way door. Someone hauling a panel as narrow as
  it goes is asking for the space, not for 180px of it, and the overshoot on
  each side is what keeps merely bottoming out from tripping either. The width
  they had is kept, so re-expanding is not a reset. `RAIL_COLLAPSED_WIDTH`
  restates `.rail.collapsed`'s 56px in TS because the unfolding drag has to
  measure from what is on screen.
- **There is no Save button — every exploration saves itself.** Saving was a
  manual ＋ until v7.16.0, and forgetting it lost the sitting on tab close.
  `useAutosave` now writes the same blob without being asked. It is worth
  knowing *why it doesn't write constantly*: a save is a whole-blob POST, and
  the 2-second debounce is what collapses a burst into one write. That
  debounce is also, on its own, what prevents mid-stream saves — a streaming
  answer rewrites the last chat turn on every chunk, so each chunk pushes the
  timer out and the quiet period only arrives once the stream settles. No
  "is it streaming?" flag is consulted, which matters because that flag is
  component-local to `useConversation` and never reaches the store.
- **The exploration boundary is explicit, and both sides of it flush.** A row
  begins at ✎ New Exploration or on opening a saved one; re-seeding *inside*
  an exploration continues the same row (Patrick, 2026-08-29). Both boundary
  handlers call `flush()` before clearing, because the last couple of seconds
  of the exploration being left are still sitting in the debounce — dropping
  them would be the exact loss the autosave exists to end.
- **The id and the conversation move together, or explorations copy each
  other.** Two races were found in browser testing and both had the same
  shape: an autosave firing while the id pointed at one exploration and the
  store held another. `openExploration` therefore **awaits the restore before
  setting `openSessionId`** — setting it up front let a save in the async gap
  write the outgoing conversation into the row being opened, so both rows
  ended up with the same history. `useAutosave.save()` likewise captures the
  id *and* the state synchronously, before it awaits a name, because leaving
  an exploration clears the store on the very next statement.
- **A name is written once, then left alone.** The first save asks the server
  to name the exploration after its conversation (`POST /api/sessions/title`,
  the summarizer's second entry point); later saves reuse it. Once, because it
  costs a model call *and* because the reader may have renamed the row from
  its ⋮ menu — re-titling every two seconds would overwrite them. Titling is
  its own route rather than a step inside the save for the same reason: model
  latency has no business on a path that runs all afternoon. If it can't be
  reached, the fallback is the reader's own first message.
- **A save must never write less than is already stored.** `saveConversation`
  compares the prose it is about to send against the last body it wrote for
  that conversation and refuses to shrink it. This is not defensive
  programming: browser testing produced exactly this loss — a completed
  3,000-character answer came back as an empty failed turn, because a blanket
  unload flush wrote a *reopened* exploration's thinner in-memory copy over
  the finished one on disk. A whole-blob overwrite makes that the difference
  between a small bug and destroyed work.
- **The unload path is deliberately different from every other save.** It skips
  the titler (naming the exploration from the reader's own words instead) and
  sends the request `keepalive`. Awaiting a round-trip while the document is
  being torn down is how the last save — the one that matters most — was
  silently cancelled and lost. It also flushes only conversations this tab has
  actually written, for the reason above.
- **`openSessionId` is tracked in the shell rather than the store**, because
  it's a fact about this *session of use* — which row to mark, and which one
  the autosave overwrites — not about the graph.
- **The autosave reports nothing, and that was a decision** (Patrick,
  2026-08-29). Dropping the button dropped the only signal that work was safe,
  so the first cut moved a "Saving… / Saved" label onto the open row. On
  screen it read as chatter on a rail that is otherwise quiet, and it went.
  The row appearing in the list is the whole signal.
- **Both list mutations are optimistic.** Rename and delete change the row
  immediately and re-read afterwards, so a failure corrects itself on the next
  read. That's safe here specifically because neither is destructive to
  anything unrecoverable — a rename is a label, and a delete already sits
  behind a menu.

## The main pane

`Atlas` owns a `view` (`workspace` | `library`) that rail entries switch. The
workspace stays **mounted but hidden** behind the library rather than
unmounting: the graph and the conversation are expensive live state, and
visiting the library is a detour, not a teardown. (`Sources` grew a
`variant="pane"` for this; the drawer shape is still there and still used by
the tour.)

Two controls float over the canvas rather than the pane, and the distinction
matters: the detail panel is a **sibling** of `.canvas-wrap`, so anything
anchored to the pane sits on top of it. The 🎓 that reopens a collapsed
assistant learned this the hard way — parked at the pane's top-right it
covered the detail panel's own ✕ and trapped the reader inside it. It renders
with the graph overlays now, so the canvas yields when the panel opens and the
button yields with it.

## Who uses it

`Atlas.tsx` renders `SideBar`, owns `view` / `railOpen` / `openSessionId` /
the save notice, and calls `useSessions`. Nothing else imports from here.

## How it's verified

`tsc -b` strict + oxlint + prettier. The rename/delete backing is pinned
server-side (`test/atlas/routes/test_sessions.py`), including that a rename
does **not** move `updated_at` — the list sorts by it, and a rename that
reshuffled would lose you the row you just labelled.
