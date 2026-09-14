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
  Teacher.tsx        — the slim shell: title row, the two folding sections
                       (Lecture / Q&A), ask form
  useConversation.ts — the stream engine: runs the 3 streams, dispatches
                       events into the store, owns panel run-state
  HopDots.tsx        — the one "working on it" indicator, shared by a
                       generating lecture button, the send/stop control, and
                       an assistant bubble awaiting its first token
  ScopePicker.tsx    — generic checkbox-scope popover: which sources the
                       assistant searches AND which lectures it uses as context
                       (open state controlled by Teacher — the two popovers
                       are mutually exclusive; ✕ or the trigger closes). Its
                       trigger renders icon + label as separate elements so a
                       narrow row can show the icon alone.
  figures/           ← sub-package: the inline-figure pipeline
    split.ts         — pairs <<FIG n>> markers with attached figures
    FigCard.tsx      — one figure card (click to enlarge)
  transcript/        ← sub-package: rendering the conversation
    BeatList.tsx     — lecture beats (click to light their papers), rendered
                       both in the Lecture section and inside a chat turn
    ChatMessage.tsx  — one turn: retrieval line, trace chips, prose+figures,
                       or a routed lecture's beats + the route line
    AnswerMarkdown.tsx — Markdown + KaTeX + [n]-citation rendering
    remarkCite.ts    — the remark plugin behind the citation chips
  teacher.css
```

Both sub-packages are clusters of single-parent components — the hybrid
structure rule's nesting case (the `graph/hooks` precedent).

## The state split (the directive, applied to the hardest case)

- **In the store:** the transcript (chat + the exploration's lecture — Save
  needs it), the highlight ids (the canvas needs them), discoveries (the graph
  and Save need them). `useConversation` dispatches; nothing is reported
  upward through props anymore — the old `onStateChange`/`initial*` prop
  plumbing and the Atlas-side duplicate are gone.
- **Panel-local, on purpose:** the input box, the `asking` and `lecturing`
  flags, the
  stream error, activeBeat/activeChat/activeChatBeat (which entry is lit is
  panel UI — only the resulting ids are global; the third addresses a beat by
  *turn* as well as index, since a conversation can hold several routed
  lectures while the Lecture section holds one), the scope pickers' exclusion sets
  (`excludedSources` — exclusion-tracked so a new source is in scope by
  default; the lecture's is the plain `lectureInScope` flag) plus which
  picker's popover is open
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
- **The lecture reads `selectLectureNodes`, not the researcher's grounding.**
  The two differ on exactly one thing — whether a discovery the filters exclude
  stays in scope — and the lecture's answer is no, because it promises to
  narrate the papers on screen. See `store/README.md`.
- **A framing choice above the button** — `Summary | History`, panel-local
  (`framing` in `Teacher.tsx`), sent per request. It sits *above* rather than
  beside the button because it is a setting the press consumes, not a second
  action: read the framing, then press. It **disables while a lecture is
  shown**, since that lecture was told under the framing selected at the time
  and a control drifting away from the beats on screen would describe the wrong
  thing — clearing the lecture frees it. Summary is the default: a chronological
  arc is a strong claim to make about an arbitrary selection, and forcing one
  produced beats about the timeline instead of the papers (see the lecturer's
  README).
- **One Lecture button, tinted the seed's gold** (v7.17.0). Each of four
  buttons used to be tinted its relation's node colour, because each mode
  narrated one relation — the button visibly belonged to the nodes it lit up.
  With one lecture whose subject is whatever the reader has scoped, there is no
  single relation to match, so it wears the seed's colour: the one node every
  lecture is anchored on. Its accessible name is "Play the lecture" rather than
  "Lecture", because the section header above is already named that and two
  controls sharing an accessible name inside one section is a screen-reader
  coin toss.
- **The panel is two folding sections** (v7.10.0 — `lecturesOpen` / `qaOpen`,
  `.panel-section` + `.section-toggle` / `.section-body`). **Lecture** holds
  the button, the intro, and the shown lecture's beats; **Chat** holds the
  conversation. Each has a caret row that names it and folds it. Details that
  make the fold safe: the states are **initial values only** (open one and it
  stays open for the session); Lecture starts
  **folded** because a control in the panel's prime vertical space is not
  what most turns need, while Chat starts **open** because it is what the
  composer writes into; the tour **stages both open** (`stagedOpen`, the same
  contract `GraphControls` has), which is also how a first-time reader learns
  the lectures exist; asking a question **unfolds Chat** (a turn landing in a
  folded section reads as nothing happening); and while Lecture is folded, a
  **generating lecture still reports itself** on its caret row with the shared
  spinner, since its button's own dots are out of sight. Opening replays the
  panel's one entrance (`rise` + `fade`, quicker); folding is instant, and
  `prefers-reduced-motion` drops both.
- **The section headers are pinned** (`position: sticky` on `.section-head`).
  A long conversation used to bury its own header: folding the chat away, or
  reaching its scope pickers, meant scrolling all the way back to the top
  first (Patrick, 2026-08-16). A sticky box is confined to its own containing
  block, so the two headers don't stack up — the Lecture one leaves with its
  section and the Chat one takes the top from it — and the row is opaque
  because turns now pass behind it.
- **Each section reports its own work on its header**, with the app's shared
  `.spin` rather than `HopDots`: the hopping dots are a *voice* ("an agent is
  composing" — a lecture button, the send control, a bubble awaiting its first
  token) and a header is a status line, the same distinction the trace chips
  draw. Lecture shows it only while **folded**, since the button's own hopping
  dots are the better readout when open. Chat shows it whenever the
  agent is working, folded or not — with the header pinned, it is the only
  thing still on screen while a reader scrolls back through history.
- **Lecture buttons are cached toggles** (`toggleLecture` in `useConversation`):
  the button is a show/hide switch over the exploration's lecture. First press
  streams and stores it (`lectureStarted`/`beatAdded`); pressing it while shown
  hides it (`lectureHidden`, beats kept) and pressing it while hidden reveals
  what is there — live if still streaming, instant if done
  (`lectureShownAgain`). Note what a second press is *not*: a re-ask over a
  changed scope. That is `clearLecture` then press again — and it stayed that
  way when lectures became askable in words (v7.20.0), because the two are
  genuinely different requests. A button press means "show me the lecture"; a
  *message* is a reply the reader can scroll back to, so "lecture me on these
  five instead" appends a turn rather than overwriting the slot. That is the
  whole reason routed beats live on the turn (`chatBeatAdded`) and not here.
- **The composer routes, and says so** (v7.20.0 — `send` / `reroute` in
  `useConversation`). One bar, four destinations. Three are still decided on
  plain facts before any model is involved — a pasted arXiv id (`ID_RE`), a
  mention the reader picked from the dropdown, an unresolved `@phrase` — and
  those stay free and exact. Only the fourth asks `POST /api/route`, because
  "teach me these papers" and "which of these used dropout" differ in their
  words and nowhere else.

  Three things make paying for that acceptable, and all three are load-bearing:

  - **The classify is skipped whenever a lecture is impossible** — no graph, or
    nothing visible to lecture about. Not an optimization: with one destination
    there is no choice to buy.
  - **Every routed turn says which assistant answered and offers the other**
    (`routedTo` on the turn, `.chat-routed` + `reroute`). A misroute costs one
    click, not a wrong answer the reader has to notice. The offer is absent
    when the reader chose the destination themselves — the button, or a
    correction they already made — since there is then nothing to second-guess,
    and a correction deliberately carries none so the two answers can't
    ping-pong.
  - **Stop reaches the classify** (`routeCtrl`, aborted by `stopAsk`). A
    message stopped while it is still being routed has no turn yet, so
    `askCtrl` has nothing to abort — without its own controller the reader's
    Stop is silently ignored and the answer they cancelled starts a moment
    later.

  A routed lecture streams on **`askCtrl`**, not `lectureCtrl`: it is a chat
  turn, so the next message supersedes it and the Lecture section's own
  lecture — which may be streaming at the same time — is untouched. Its scope
  is the same `selectLectureNodes` the button uses; the router decided which
  *agent* answers, not which papers, and rescoping because a lecture was asked
  for in words would make one request mean two things.
- **The lecture streams on its own controller** (`lectureCtrl`, with
  `lecturing` driving the button's hopping dots); the chat has its own. So a
  lecture keeps generating in the background when you hide it or ask a
  question — neither interrupts the other. `onBeat` only drives the graph
  highlight while the lecture is on screen (`shownRef`) and its exploration is
  the one being read.
- **The played lecture rides along on a Q&A** (`useConversation.ask`): every
  `ask` packs it (trimmed to each beat's heading + text, titled via the shared
  `LECTURE_TITLE`) into `streamAsk`'s `lectures`, so the researcher can build
  on a story the student already watched instead of re-deriving it (and
  re-paying the tokens). The backend budgets the block. A **🎓 scope picker**
  (the same `ScopePicker` the sources use) says whether it is fed —
  `lectureInScope` in `Teacher.tsx`, ticked by default, since a lecture the
  reader just heard is context they expect an answer to build on. A quiet line
  above the ask bar notes when it is in play.
- **The lecture and the conversation no longer take turns** (v7.10.0). They
  used to share one scroll, gated on which mode was shown: a shown lecture took
  the panel over, and **asking a question hid the lecture** (`ask` dispatched
  `lectureHidden`) so the two could never stack. Sections made that unnecessary
  and then wrong — a reader deep in a lecture would ask a follow-up and watch
  the beats they were reading vanish — so that dispatch is gone and a shown
  lecture stays shown. `selectVisibleBeats` keys off `lectureShown`, which means
  only whether the section shows it; the chat is always the full list. Both
  remain a pure render choice over persistent state: the lecture and the chat
  both live in the store.
- **Two Clears, one per section** — `clearLecture` (stop it if loading,
  `lectureDropped`, unlight the graph) sits on the Lecture caret row, and
  `clearChat` (`chatCleared` + a fresh session id) is the bin in the composer,
  which belongs to Chat. It was one contextual button until v7.10.0; with both
  sections on screen at once, a single button could no longer say which of the
  two it would wipe.

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

**Where the controls live, and why.** Each control sits on the thing it acts
on. The panel's title row holds only the title and the ✕. The **🎓 and 📚
scopes ride the Chat caret row** (v7.10.0): they bind the *researcher* — what
it may read and search when it answers — not the lecturer above, and both a
peer "Grounding" section and a slot in the panel header would imply they
scope everything (Patrick's call, and the reason they landed here). The
**🔍 direct-search toggle and the ▽ filters joined them there in v7.11.0**
(the toggle then went in v7.18.0, replaced by typing `@` — see
`../mentions/README.md`),
for the same reason and out of the same place.

**The ask bar holds the question and nothing else** (v7.11.0). Those four
controls all used to sit *inside* the pill, which is what made it read as
clutter: the one thing you came here to use — a box to type in — looked like a
toolbar with a text field wedged in it. So the pill was emptied. With **no
graph** there are no sections to receive them, so the same single
`sourcePicker` / `searchControls` elements render instead in a **chip row
directly beneath the bar** (`.ask-tools`) — one of two places, never both.
Beneath rather than above: you read the question first, then what bounds it,
and the row is far enough from the text field to stop being chrome around it.
The bar and that row are wrapped together in `.ask-dock`, which is what the
landing surface's FLIP measures — the two drop from the optical centre to the
bottom as one thing on the first question, and a row that snapped while the
bar slid would read as two unrelated controls.

On the Chat row every trigger is its icon alone (the popover shows the truth
once open, an accent fill marks an armed toggle or a narrowed scope, and the
tooltip spells it out); in the landing tool row there is width for the labels,
which is where a first-time reader meets them. Popovers follow the room:
**upward** from the tool row, which sits at the bottom of the page under the
bar, and **downward** from the pinned Chat row.
The 📚 picker appears at **one** source, not two (v7.2.0): the old `> 1` gate
read a lone source as leaving no choice to make, but "use it / don't" is a
choice, and hiding the control meant a reader with one uploaded book had no
way to ask a question *without* it. `ScopePicker` adapts to that size rather
than being shown as-is — a single item drops the All/None bulk actions, which
would only duplicate the checkbox beneath them, and labels itself "1 source"
instead of claiming "All sources". Clear takes the send button's round shape but stays muted: it is the
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

**The docked panel is titled "AI Teacher & Discovery"** (v7.10.0). It named
only the agent before ("AI teacher"), which is the implementation rather than
the offer; "Discover" alone was tried on the way and dropped for losing the
teaching half. The panel does both, so the title says both. In *prose* — tour
steps, the controls panel's alt-drag hint — the thing is called **"the
assistant"**, which is what the rest of the copy already called it, rather
than repeating the title.

## Nothing may push the panel wider than it is (v7.10.0)

`.teacher-scroll` is `overflow-y: auto`, and a box with one visible axis and
one scrolling axis computes the visible one to `auto` too — so the transcript
**is** a horizontal scroller, and anything unwrappable in it (a bare URL, a
DOI, a long identifier) turned the docked chat into a sideways-scrolling one.
The fix is `overflow-wrap: anywhere` on that box, inherited by every bubble,
beat, trace chip and hint below it; `anywhere` rather than `break-word`
because it also shrinks the box's min-content width, which is what lets the
flex column hold the panel to its own width instead of being widened from
inside. Genuinely unwrappable content gets a scroller of its own instead:
`.md pre`, `.md table` and (new) `.katex-display`, which KaTeX ships with no
overflow at all. Deliberately **not** `overflow-x: hidden` on the panel — that
hides the symptom and silently clips those three.

## How it's verified

`tsc --noEmit` strict + oxlint, plus `test/teacher/Teacher.test.tsx` — the
lecture fold's default and its `stagedOpen` unfold, and which of the two homes
each ask-binding control (📚 scope, ▽ filters) renders in
for each shape — including that none of them is inside the bar. Browser-milestone items: a
lecture lighting beats as they stream, a researcher answer with trace chips +
an inline figure, the library chat with a scope subset, Clear detaching
follow-up context, and a save→restore round trip rehydrating the whole
conversation.


## The chat bar is the app's only text input (v7.6.0)

The header search box moved in here. Searching and asking were always two ways
of saying "find me papers about this", and having them in two boxes meant
picking the box before you knew which one you wanted.

`Teacher` owns the two pieces of state that decides: `direct` (the 🔍 **Find
papers** toggle) and `searchOptions` (the **Filters** popover). Both controls
travel with `ScopePicker`, always the same row as it, for the reason that one
does: they belong to the thing you are about to send. They rendered inside the
ask form until v7.11.0 — see "Where the controls live" above for where they
went and why. `search/SearchControls` draws them; `search/useDirectSearch`
runs the scout.

**Three destinations, decided in `submitQuestion` before any model runs:**

1. a pasted arXiv id/URL → straight to the graph (`ID_RE`, no LLM at all),
   checked **first**, because you pasted the paper and there is nothing left
   to search for whichever toggle happens to be armed;
2. `direct` armed → the paper scout, alone;
3. otherwise → the researcher, as always.

Two consequences worth knowing:

- **A scout search has no reducer of its own.** It drives `turnStarted` →
  `traceAdded` → `answerSet` → `paperRefsSet` — the same path a streamed
  answer walks — so its result is an ordinary assistant turn that
  `ChatMessage` renders, a click reseeds, and a saved session keeps it. The
  one addition was `answerSet`, because this path's later text *supersedes*
  its earlier text (the cached list, then the scout's) rather than continuing
  it, which `tokenAppended` can't express.
- **`streaming` is `asking || searching`.** One bar, one busy state: neither
  mode can be fired while the other runs, and the send button shows the same
  hopping dots either way.

The filters ride on `ask` too, not just on a scout search — see
`search/README.md` for why they belong to the bar rather than to one of its
modes.


## The lecture intro says what a lecture will leave out (v7.7.0)

`.lecture-intro` above the Lecture button carries a conditional sentence: when
papers on the graph hang off *another* paper rather than the seed, it names how
many.

**The sentence was inverted in v7.17.0, and that inversion is the point.** It
used to say no lecture covered them ("Re-seed on one to hear its story"),
because each mode was scoped to the seed's own neighbours and a satellite fell
outside every one of them — silence there would have read as the lecture
quietly skipping papers rather than as a stated boundary. A lecture now
narrates whatever is scoped, so satellites ARE covered, and the sentence says
so ("That includes the 3 papers you expanded"). Same count, opposite claim:
worth stating either way, because a reader who has been expanding the graph
needs to know which of the two they are getting.

The count comes from `selectSatelliteCount`, which asks *is this joined to the
seed by an edge?* rather than reusing the frontend's own `_origin` layout hint.
It used to match the backend's scoping predicate exactly, which was the reason
to prefer it; now that nothing on the backend scopes by relation, it is simply
the honest reading of "hangs off another paper". It counts over the *grounding*
nodes, so filtering a satellite off the canvas drops it from the count — the
number tracks what the lecture will actually cover right now.
