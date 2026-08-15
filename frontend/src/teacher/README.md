# `src/teacher`

The unified assistant — the old 743-line `Teacher.tsx` split along its real
seams. One conversation in two shapes: with no graph it is the **landing
surface**, a centred chat that is the app's front door and needs neither a
graph nor an uploaded library; with a graph it docks as a side panel beside
the map. Its capability levels up separately — no graph → the researcher,
seedless (the literature plus whatever sources you've uploaded); graph open →
lecture buttons + agentic Q&A (the lecturer and researcher).

```
teacher/
  Teacher.tsx        — the slim shell: header, modes, scroll, ask form
  useConversation.ts — the stream engine: runs the 3 streams, dispatches
                       events into the store, owns panel run-state
  HopDots.tsx        — the one "working on it" indicator, shared by a
                       generating lecture button, the send/stop control, and
                       an assistant bubble awaiting its first token
  ScopePicker.tsx    — generic checkbox-scope popover: which sources the
                       assistant searches AND which lectures it uses as context
                       (open state controlled by Teacher — the two popovers
                       are mutually exclusive; ✕ or the trigger closes). Its
                       trigger renders icon + label as separate elements so
                       the ask bar can show the icon alone.
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
  only the resulting ids are global), the scope pickers' exclusion sets
  (`excludedSources`/`excludedLectures` — exclusion-tracked so a new
  source/lecture is in scope by default) plus which picker's popover is open
  (`openScope`, one shared slot so the two popovers can't overlap), the
  lightbox, the abort/session refs, and whether the transcript is currently
  following its own bottom (a ref, not state — it changes on every scroll
  event and nothing renders from it). The **source list itself** is NOT
  local anymore: it reads live from the store's `library` slice, which the
  Sources drawer reloads on every upload/delete — the picker used to sit on
  a mount-time fetch and not appear until a page reload (Patrick's
  2026-07-11 report).

## Design decisions worth knowing

- **The transcript follows the bottom while an answer builds — but only if
  you're already there.** Trace chips, tokens and beats all arrive at the end,
  and without this they grow past the fold: the reader watches the agent work
  right up until the work scrolls out of sight. So a content change scrolls
  to the bottom *conditionally*, gated on a `following` ref that a scroll
  handler keeps up to date. Scroll up mid-answer to re-read something and the
  transcript stops chasing — being yanked back down is worse than the problem
  this solves — and scrolling back down resumes it. The bottom test carries a
  40px tolerance, which is not slop: `.chat`'s entrance leaves the last
  element 16px below its resting place for the length of the animation, so a
  tight test would read "not at the bottom" exactly while a turn arrives. The
  scroll is instant, never smooth: smooth can't keep up with SSE frames, and
  several in flight at once judder against each other.

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
  `epoch`, which now bumps on **Home and restore only** — a graph load
  leaves the panel, its scroll position and its run state alone, because
  the conversation survives a re-seed and remounting would scroll the
  reader back to the top. In-flight streams are aborted on the seed change
  rather than on an unmount that no longer happens; the transcript resets or
  restores via the store, not via remount props.
- **The provider rides on every question, graph or not.** With a graph it
  keeps the researcher's expand/search/hydrate in the same id space as the
  nodes on screen; graph-free there's no graph to match, but it still decides
  which backend the paper search hits — and therefore whose ids come back on
  the citations a reader may click to build a graph from. `streamAskSources`
  omitted it until v6.14.0, which pinned the landing chat to the default
  backend whatever the dropdown said (see `docs/bugs.md`).
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

The shell renders `Teacher` in **two shapes from one instance** — `landing`
(no graph: it owns the body as a centred column, and is the app's front
door) and docked (a graph is up). Only the class changes, deliberately: the
shell keeps the component at one position in the tree, so entering graph
mode collapses the landing chat into the side panel without remounting it,
and the answer you were reading keeps its scroll position. It is keyed on
`epoch` — which bumps on Home and restore only, for that same reason — and is
hidden-not-unmounted when collapsed, so the conversation survives toggling.
Everything else flows through the store: highlights → the canvas, discoveries
→ the explorer's sim merge, transcript → Save.

**Where the controls live, and why.** The source scope and Clear both sit in
the **ask bar** rather than the panel head. On the landing surface the head
has no title and no ✕, so anything left there floats in empty space with
nothing to belong to — and the scope was never really header furniture
anyway: it qualifies the question you are about to ask, so it travels with the
ask. In the bar the scope trigger is its icon alone (the popover shows the
truth once open, an accent fill marks a narrowed scope, and the tooltip spells
it out), and its popover opens **upward**, since the bar sits at the bottom of
the page. Clear takes the send button's round shape but stays muted: it is the
destructive one and must not compete with the control you came to press. The
send itself doubles as **stop** while an answer streams — hopping dots at
rest, a stop square on hover — so the thing that says "working" is also the
thing that ends it, and it is never disabled mid-flight.

## Motion

One gesture, one rhythm, both defined in `teacher.css`.

- **`rise` + `fade`** — up from 16px below, the entrance for everything that
  arrives: the landing greeting, the composer and its context note a beat
  later (they move as one thing — the note belongs to the bar), every chat
  turn, and every agent trace chip.
- **They are two animations on purpose, and must stay that way.** The fade
  should *lag* the rise, so the element surfaces out of the background
  instead of sliding in already-formed. Expressing that as a mid-keyframe
  (`55% { opacity: 0.25 }`) doesn't work: a timing function applies between
  each *pair* of keyframes, so the fade decelerated into that stop and
  accelerated out of it — a hitch that reads as dropped frames, which is
  exactly how it was reported. Split in two, each curve is a single smooth
  interval: `--ease-rise` eases out, `--ease-fade` eases in. Retune either
  alone; don't merge them back.
- **Tuning history**, since this took three passes: 8px over 0.32–0.45s read
  as a flicker; 16px over 0.45–0.7s with the lagged fade is the current
  setting. The knobs are the travel, the two curves (named on `.teacher`),
  and the durations.
- **Trace chips are the one place the motion does real work** rather than
  polish. They arrive one at a time while the agent runs, and they *are* the
  progress report — one rising into place reads as "something just
  happened", where a chip silently appearing in a stack does not.
- **The turn entrance is plain CSS, not state-driven** — and that is the
  design, not laziness. A CSS animation fires when an element is *created*,
  which is exactly the trigger: once per turn. A streaming answer re-renders
  on every token, and an answer can be re-lit or re-themed; none of that
  restarts an animation, so prose can never twitch mid-stream. It also means
  a graph load leaves the transcript still — the conversation survives a
  re-seed *without remounting*, so there is nothing to replay. A restore is
  the one case where every bubble plays at once, which is right: that is the
  panel arriving.
- **The greeting/composer entrance is scoped to `.landing.empty`** so it
  can't replay on the docked panel. `display: none` → `block` restarts CSS
  animations, so an unscoped rule would re-run the entrance on every ✕ and
  re-open of the side panel.
- **The composer's drop is a FLIP** (`Teacher.tsx`), because it can't be
  anything else: going from optically centred with the greeting to pinned at
  the bottom is a flex-layout change, and CSS cannot transition those. So the
  bar's position is recorded each time the empty/non-empty state settles, and
  once the browser has placed it anew it's animated from where it *was*.
  Nothing about the layout is faked — only a transform plays over the top.
  Its duration is paced with `rise-in` and eased identically, at the longer
  end of the range because it travels much further; retune the two together.
  Keyed on that state flip alone and never on every render: reading
  `getBoundingClientRect` forces layout, and this component re-renders on
  every streamed token.
- **Two wait indicators, and the split is deliberate.** `HopDots` means *an
  agent is composing* — the send button mid-answer, a generating lecture, a
  bubble waiting on its first token. The shared `.spin` primitive
  (`atlas.css`) means *a step is running*: a scout trace chip while its
  worker searches. They were briefly the same thing, and using the dots
  everywhere flattened the difference — a chip is an item in a list, not a
  voice. `HopDots`' `label` prop is its a11y contract: named where the dots
  *are* the message, silent inside a control that already announces the state
  (the send button becomes "Stop generating").
- **A pending chip's spinner is absolutely positioned in the chip's right
  edge**, not trailing the text. Inline it collided with the query it belongs
  to, and a trace row is variable-length — the corner is the only stable
  place for it. Absolute keeps it out of the inline flow entirely, so no flex
  conversion and no wrapping surprises on a long query.
- **Everything has a `prefers-reduced-motion` path.** The CSS entrances drop
  out in the block beside the keyframes; the FLIP checks `prefersStill()`
  itself, since a scripted animation can't be reached by a media query.

## How it's verified

`tsc --noEmit` strict + oxlint. Browser-milestone items: a lecture lighting
beats as they stream, a researcher answer with trace chips + an inline figure,
the library chat with a scope subset, Clear detaching follow-up context,
and a save→restore round trip rehydrating the whole conversation.
