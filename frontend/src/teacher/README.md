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
  ScopePicker.tsx    — which sources the assistant may search
  figures/           ← sub-package: the inline-figure pipeline
    split.ts         — pairs <<FIG n>> markers with attached figures
    FigCard.tsx      — one figure card (click to enlarge)
    Lightbox.tsx     — the full-screen viewer (Escape closes)
  transcript/        ← sub-package: rendering the conversation
    HistTrace.tsx    — the history lecture's backfill hops
    BeatList.tsx     — lecture beats (click to light their papers)
    ChatMessage.tsx  — one turn: retrieval line, trace chips, prose+figures
  teacher.css
```

Both sub-packages are clusters of single-parent components — the hybrid
structure rule's nesting case (the `graph/hooks` precedent).

## The state split (the directive, applied to the hardest case)

- **In the store:** the transcript (chat/beats/histTrace — Save needs it),
  the highlight ids (the canvas needs them), discoveries (the graph and
  Save need them). `useConversation` dispatches; nothing is reported
  upward through props anymore — the old `onStateChange`/`initial*` prop
  plumbing and the Atlas-side duplicate are gone.
- **Panel-local, on purpose:** the input box, asking/teaching flags, the
  stream error, activeBeat/activeChat (which entry is lit is panel UI —
  only the resulting ids are global), the scope picker's library list and
  checked set, the lightbox, and the abort/session refs.

## Design decisions worth knowing

- **The figure interleaver** (`figures/split.ts`): `FIG_TAIL` holds back a
  partial `<<FIG` marker at the end of streaming prose so it never flashes
  raw mid-chunk; an invented slot's marker vanishes without gluing its
  surrounding paragraphs; figures whose marker never appeared render at
  the bubble's end (also covers old saved sessions without slots).
- **Streams carry FULL node shapes**: `useConversation` selects the seed
  *node* (`selectSeedNode` — the compact `graph.seed` header lacks the
  fields the backend's typed boundary requires) and the grounding set
  (`selectGroundingNodes` = graph ∪ discoveries, deduped) from the store.
- **Session mechanics:** a client-generated `session_id` keys the backend's
  chat history; Clear mints a new one, so a cleared conversation also
  detaches from server-side context. The panel remounts per workspace
  `epoch` (fresh run-state per graph); the transcript itself resets or
  restores via the store, not via remount props.
- **Wire deltas absorbed here:** `onDiscovery` (was `onNodes`), error
  `{message}`, no `discard` handler (the researcher's pre-answer narration is
  never streamed), `BackfillTrace` naming.

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
