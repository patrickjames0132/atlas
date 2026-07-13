# `src/teacher`

The unified assistant panel — the old 743-line `Teacher.tsx` split along
its real seams. One docked panel whose capability levels up with context:
no graph + a library → the graph-free library chat (the librarian); graph
open → lecture buttons + agentic Q&A (the lecturer and researcher).

```
teacher/
  Teacher.tsx        — the slim shell: header, modes, scroll, ask form
  useConversation.ts — the stream engine: runs the 3 streams, dispatches
                       events into the store, owns panel run-state
  ScopePicker.tsx    — generic checkbox-scope popover: which sources the
                       assistant searches AND which lectures it uses as context
  figures/           ← sub-package: the inline-figure pipeline
    split.ts         — pairs <<FIG n>> markers with attached figures
    FigCard.tsx      — one figure card (click to enlarge)
  transcript/        ← sub-package: rendering the conversation
    BeatList.tsx     — lecture beats (click to light their papers)
    ChatMessage.tsx  — one turn: retrieval line, trace chips, prose+figures
    AnswerMarkdown.tsx — Markdown + KaTeX + [n]-citation rendering
    remarkCite.ts    — the remark plugin behind the citation chips
  teacher.css
```

Both sub-packages are clusters of single-parent components — the hybrid
structure rule's nesting case (the `graph/hooks` precedent).

## The state split (the directive, applied to the hardest case)

- **In the store:** the transcript (chat + the per-mode lecture cache — Save
  needs it), the highlight ids (the canvas needs them), discoveries (the graph
  and Save need them). `useConversation` dispatches; nothing is reported
  upward through props anymore — the old `onStateChange`/`initial*` prop
  plumbing and the Atlas-side duplicate are gone.
- **Panel-local, on purpose:** the input box, the `asking` flag and the
  `loadingModes` set (which lectures are streaming), the
  stream error, activeBeat/activeChat (which entry is lit is panel UI —
  only the resulting ids are global), the scope picker's library list and
  checked set, the lightbox, and the abort/session refs.

## Design decisions worth knowing

- **`Lightbox.tsx` moved out to `../figures/`** (root-level, not nested here)
  once the detail panel's own paper figures became a second consumer — the
  hybrid structure rule promotes a component the moment it's no longer
  single-parent. `FigCard.tsx` stays here; it's still teacher-only (the chat
  bubble's inline-figure card styling, not reused elsewhere).
- **The figure interleaver** (`figures/split.ts`): `FIG_TAIL` holds back a
  partial `<<FIG` marker at the end of streaming prose so it never flashes
  raw mid-chunk; an invented slot's marker vanishes without gluing its
  surrounding paragraphs; figures whose marker never appeared render at
  the bubble's end (also covers old saved sessions without slots).
- **Streams carry FULL node shapes**: `useConversation` selects the seed
  *node* (`selectSeedNode` — the compact `graph.seed` header lacks the
  fields the backend's typed boundary requires) and the grounding set
  (`selectGroundingNodes` = `(selected ∩ visible) ∪ discoveries`, deduped)
  from the store — so a hand-picked marquee selection on the canvas scopes
  both the lecture and the Q&A. The panel surfaces an active pick as a note
  above the ask box (`N hand-picked papers`), mirroring the lecture-context
  note.
- **Session mechanics:** a client-generated `session_id` keys the backend's
  chat history; clearing the chat mints a new one, so a cleared conversation
  also detaches from server-side context. The panel remounts per workspace
  `epoch` (fresh run-state per graph); the transcript itself resets or
  restores via the store, not via remount props.
- **Wire deltas absorbed here:** `onDiscovery` (was `onNodes`), error
  `{message}`, no `discard` handler (the researcher's pre-answer narration is
  never streamed). Lectures stream beats only — they never expand the
  graph, so the lecture handler has no trace/discovery callbacks.
- **Lecture buttons are colour-coded to their relation** (`MODES` in
  `Teacher.tsx`): each mode narrates one graph relation, so its button is tinted
  that relation's node colour (`REL_COLOR` via a `--c` custom property, the same
  hex the filter chips and legend dots use) and shows only that relation's short
  node-type word ("References" / "Landmarks" / "Latest" / "This paper"), centred
  — the button visibly belongs to the nodes it lights up. The full lecture name
  (`label`) lives in the button's tooltip/aria-label and in the **"Now playing"
  header** above the transcript (`.lecture-now`, also tinted `--c`), so a long
  name never clutters the button. The idle/hover tints are `color-mix` alphas of
  `--c`; the shown (`.active`) button fills solid with it. The lecture section
  itself is ruled off under the panel title with a divider and a one-line intro
  (`.lecture-intro`). (The `--lecture` periwinkle triple now only tints the
  beat/chat/trace surfaces, not the buttons.)
- **Lecture buttons are cached toggles** (`toggleLecture` in `useConversation`):
  each of the four modes is a show/hide switch over its cached beats. First
  click on a mode streams and caches it (`lectureStarted`/`beatAdded` write the
  mode's slot — `beatAdded` carries its mode so a background stream fills the
  right slot); re-clicking the shown mode hides it (`lectureHidden`, cache
  kept) and clicking a hidden mode that's cached or still loading reveals it
  instantly (`lectureShown`, no re-fetch). A run dropped before it finishes
  (cleared) drops its partial via `lectureDropped`, so the next click
  regenerates rather than reloading half a lecture.
- **Everything streams in parallel** — the single "teaching" flag and shared
  abort controller are gone. Each in-flight lecture has its own controller in a
  `Map<mode, AbortController>` (`loadingModes` state drives the buttons' hopping
  dots); the chat has its own. So a lecture keeps generating in the background
  when you deselect it, ask a question, or start another mode — nothing
  interrupts anything else. `onBeat` only drives the graph highlight when its
  mode is the one on screen (`shownModeRef`); background lectures stay quiet.
- **Played lectures ride along on a Q&A** (`useConversation.ask`): every `ask`
  packs the transcript cache's lectures (trimmed to each beat's heading + text,
  titled via the shared `LECTURE_TITLES`) into `streamAsk`'s `lectures`, so the
  researcher can build on a story the student already watched instead of
  re-deriving it (and re-paying the tokens). The backend budgets the block. A
  **🎓 scope picker** (the same `ScopePicker` the sources use) filters which
  played lectures are fed — tracked in `Teacher.tsx` by **exclusion** (default
  none excluded = all fed), so a lecture played after the user last touched the
  picker is included automatically; `onAsk` passes the checked modes to `ask`. A
  quiet line above the ask bar notes how many are in play.
- **One panel, two views** (`Teacher.tsx`, gated on `activeMode`): a shown
  lecture takes over the scroll — the "Now playing" header + its beats — while no
  shown lecture means the Q&A chat. Selecting a lecture enters the lecture view;
  **asking a question hides the lecture** (`ask` dispatches `lectureHidden`) to
  drop into the Q&A view, so beats and chat never stack together. Neither is
  lost across the switch: the lecture stays cached (its button lit-as-cached, its
  background stream uninterrupted — re-select to return), the chat stays in the
  store. This is why `selectVisibleBeats` keys off `activeMode` and the chat is
  always the full list — the view is a pure render choice over persistent state.
- **Clear is contextual** — a shown lecture → clear just that lecture (stop it
  if loading, `lectureDropped`, unlight the graph); no lecture shown → clear the
  Q&A chat (`chatCleared`) and mint a fresh session id. The button relabels
  ("Clear lecture" / "Clear chat") to say which it'll do.

## Who uses it, and how/why

The shell renders `Teacher` (keyed on `epoch`, hidden-not-unmounted when
collapsed so the conversation survives toggling). Everything else flows
through the store: highlights → the canvas, discoveries → the explorer's
sim merge, transcript → Save.

## How it's verified

`tsc --noEmit` strict + oxlint. Browser-milestone items: a lecture lighting
beats as they stream, a researcher answer with trace chips + an inline figure,
the library chat with a scope subset, Clear detaching follow-up context,
and a save→restore round trip rehydrating the whole conversation.
