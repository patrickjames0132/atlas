# `src/shell`

The app's frame: the collapsible left rail, and the shell-level state that
decides what fills the main pane.

```
shell/
  SideBar.tsx    — the rail: brand + seed, New graph, saved graphs, Library,
                   Settings, theme, tour, and the data-source picker
  useSessions.ts — the saved-session list and its CRUD
  shell.css      — the rail, its menus, and the save confirmation
```

## Why the header became a rail (v7.8.0)

A top bar spends the scarcest axis — vertical — on chrome that is mostly idle,
and it can't be put away. A rail spends the plentiful one and folds to 56px
when the map wants the room. It's the shape ChatGPT and Claude both settled
on, and this is a deliberate copy of it rather than a variation.

The move also let the **saved graphs** stop hiding behind a drawer button. A
thing you accumulate should be visible; that band is what made the rail worth
building, and the Sessions drawer retired into it.

## Design decisions worth knowing

- **Three bands, one scroller.** Top (collapse toggle + brand + seed title +
  New graph) and bottom (data source, Save, Library, Settings, theme, tour)
  are fixed; only the saved list scrolls, so both fixed bands stay reachable
  however many graphs have piled up.
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
  am I". Only the labels are controls-adjacent; the brand row's *only* button
  is the collapse toggle, which keeps `.rail-item`'s symmetric padding so its
  glyph lands on the same 18px centre line as every row below it.
- **The rail resizes like the other panels** (`useResizablePanel`, 180–380px,
  persisted). The hook gained a `side` option rather than a twin: a
  left-docked panel is the exact mirror of a right-docked one, so only the
  sign of the drag differs. Width applies while expanded only — a 300px-wide
  strip of icons would be absurd.
- **Saving doesn't prompt for a name.** It names the graph after its seed and
  you rename in place from the row's ⋮ menu. The moment you want to save is
  the moment you least want a dialog, and a name is trivially fixable
  afterwards — which is what `PATCH /api/sessions/<id>` exists for (before
  it, renaming meant re-saving the whole workspace blob, so it only worked for
  the session you had open).
- **Re-saving overwrites its own row.** `openSessionId` is tracked in the
  shell rather than the store, because it's a fact about this *session of use*
  — which row to mark, and which one a re-save replaces — not about the graph.
- **The save confirmation cross-fades with transitions, not keyframes.** The ＋
  and the ✓ both stay mounted in one grid cell; a transition plays in reverse
  on its own, so the ✓ leaves the way it arrived with no second animation to
  keep in sync. The toast carries an explicit `leaving` phase for the same
  reason: unmounting on the way out is what made the first version vanish in a
  single frame. (Stacked with `grid-area: 1 / 1` rather than absolute
  positioning — absolute children take no part in layout, which collapsed both
  boxes to nothing.)
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
