# `src/teacher`

The unified assistant — the old 743-line `Teacher.tsx` split along its real
seams. One conversation in two shapes: with no graph it is the **landing
surface**, a centred chat that is the app's front door and needs neither a
graph nor an uploaded library; with a graph it docks as a side panel beside
the map. Its capability levels up separately — no graph → the researcher,
seedless (the literature plus whatever sources you've uploaded); graph open →
the lecturer as well, reached by typing rather than by pressing anything.

```
teacher/
  Teacher.tsx        — the slim shell: title row, the conversation, ask form
  useConversation.ts — the stream engine: runs the streams, dispatches
                       events into the store, owns panel run-state
  HopDots.tsx        — the one "working on it" indicator, shared by the
                       send/stop control and an assistant bubble awaiting
                       its first token
  ScopePicker.tsx    — generic checkbox-scope popover; one caller since
                       v7.21.0 (which sources the assistant searches). Its
                       trigger renders icon + label as separate elements so a
                       narrow row can show the icon alone.
  figures/           ← sub-package: the inline-figure pipeline
    split.ts         — pairs <<FIG n>> markers with attached figures
    FigCard.tsx      — one figure card (click to enlarge)
  transcript/        ← sub-package: rendering the conversation
    BeatList.tsx     — lecture beats (click to light their papers)
    ChatMessage.tsx  — one turn: retrieval line, trace chips, prose+figures,
                       or a lecture's beats + the route line
    AnswerMarkdown.tsx — Markdown + KaTeX + [n]-citation rendering
    remarkCite.ts    — the remark plugin behind the citation chips
  teacher.css
```

The `/` command menu that starts a lecture is **not** in this package — see
`src/commands/`. It belongs to the composer's grammar, beside `mentions/`,
rather than to the panel that renders the result.

Both sub-packages are clusters of single-parent components — the hybrid
structure rule's nesting case (the `graph/hooks` precedent).

## The state split (the directive, applied to the hardest case)

- **In the store:** the transcript (every turn, lectures included — Save
  needs it), the highlight ids (the canvas needs them), discoveries (the graph
  and Save need them). `useConversation` dispatches; nothing is reported
  upward through props anymore — the old `onStateChange`/`initial*` prop
  plumbing and the Atlas-side duplicate are gone.
- **Panel-local, on purpose:** the input box, the `asking` flag, the
  stream error, activeChat/activeChatBeat (which entry is lit is
  panel UI — only the resulting ids are global; the second addresses a beat by
  *turn* as well as index, since a conversation can hold several
  lectures), the source picker's exclusion set
  (`excludedSources` — exclusion-tracked so a new source is in scope by
  default) plus which
  picker's popover is open
  (`openScope`, a shared slot from when two popovers could overlap), the
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
  above the ask box (`N hand-picked papers`).
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
- **Framing is the command's second word**, `/lecture summary` or
  `/lecture history`, sent per request — or inferred by the router when the
  reader asks in words. Summary is the default a bare `/lecture` means: a
  chronological arc is a strong claim to make about an arbitrary selection, and
  forcing one produced beats about the timeline instead of the papers (see the
  lecturer's README). It was a `Summary | History` button pair above the
  Lecture button until v7.21.0, with a fiddly rule attached — disabled while a
  lecture was on screen, because that lecture had been told under whatever
  framing was selected at the time and a control drifting away from the beats
  would describe the wrong thing. A command carries its framing *in the
  request*, so there is no control left to drift.
- **The panel has no sections, and the two shapes are now one shape.** It
  stacked two folding sections from v7.10.0 to v7.21.0 — a **Lecture** section
  above a **Chat** one, each behind its own caret — because it held two things
  that had to be able to coexist. Deleting the lecture half left a lone "CHAT"
  caret whose only job was folding away the whole point of a panel already
  titled "AI Teacher & Discovery", with a ✕ beside it doing that job more
  honestly (Patrick, 2026-09-14). So both went, and with them a chain of
  things that only existed to serve them:

  - `chatOpen` and the "asking unfolds it" dispatch;
  - `stagedOpen`, the tour's prop for unfolding the Lecture section — the
    `'assistant'` stage now only *opens the panel*, which is all there is to
    do;
  - the pinned `.section-head` (sticky, so a long conversation didn't bury its
    own header — Patrick, 2026-08-16) and the **zero top padding** on
    `.teacher-scroll` that pinning forced, since a sticky child sticks below
    its container's padding. The scroller has its 12px back;
  - the section header's `.spin` readout, which reported a working agent while
    the section was folded;
  - ~180 lines of CSS (see the note at `.teacher-scroll` in `teacher.css`).

  The composer's own controls follow from the same change: with no row above
  them, there is **one home** for each rather than two — see below.
- **The newest lecture is open, the ones behind it are folded** — derived in
  `Teacher.tsx`, with an override map (`openByReader`) holding only the turns
  whose state the reader actually changed. Derived rather than stored per turn
  because the rule is a fact about the *whole conversation*: as state it would
  need an effect on every arriving lecture to fold the one before it. As a
  derivation it falls out for free, and a lecture arriving while the reader is
  reading an older one folds that older one without overwriting their choice
  about it.

  Twelve beats are fine as the newest thing on screen and unusable as the third
  lecture scrolled past, and the Lecture section that could once fold them away
  is gone — so the turn folds itself. The override map is keyed by turn index
  like `activeChatBeat`, and indices move when a failed turn is dropped, so it
  is cleared whenever the conversation is (`clearConversation`) rather than
  tracked through every mutation: a stale entry costs one caret click, and
  threading index arithmetic through the transcript would cost more.
- **Every turn is stamped with the graph it was answered over** (`turnGraphSet`
  in both `ask` and `lectureInChat`), and the panel passes the *current* seed
  id down so a turn from another graph can say so. The two counts differ on
  purpose: an answer stores `groundingNodes.length`, a lecture stores
  `lectureNodes.length`, because those are genuinely different sets (see
  `store/README.md`) and each turn should report the one it actually used.
  Skipped graph-free — there is no graph to name.
- **There is no lecture lifecycle any more** (v7.21.0), and that is the
  largest thing this package lost. A lecture used to be a *slot*:
  `conversation.lecture` plus `lectureShown`, written by a Lecture button that
  was a three-way show/hide/generate toggle (`toggleLecture`), cleared by its
  own section-level `clearLecture`, streamed on its own `lectureCtrl` so it
  ran in parallel with the chat, and fed to the researcher through a 🎓
  picker that asked whether it counted as context. Every piece of that existed
  because a lecture came from a button and so had nowhere in the conversation
  to live. It has one now (`ChatMsg.beats`), and the consequences all point the
  same way: one controller, one clear, one code path, several lectures able to
  coexist, and a lecture reaching the researcher as ordinary history.
- **The composer routes, and says so** (v7.20.0 — `send` / `reroute` in
  `useConversation`). One bar, five destinations. Four are decided on plain
  facts before any model is involved — a `/command` (`readCommand`, see
  `src/commands/`), a pasted arXiv id (`ID_RE`), a mention the reader picked
  from the dropdown, an unresolved `@phrase` — and those stay free and exact.
  Only the fifth asks `POST /api/route`, because "teach me these papers" and
  "which of these used dropout" differ in their words and nowhere else.

  Three things make paying for that acceptable, and all three are load-bearing:

  - **The classify is skipped whenever a lecture is impossible** — no graph, or
    nothing visible to lecture about. Not an optimization: with one destination
    there is no choice to buy.
  - **Every routed turn says which assistant answered and offers the other**
    (`routedTo` on the turn, `.chat-routed` + `reroute`). A misroute costs one
    click, not a wrong answer the reader has to notice. The offer is absent
    when the reader chose the destination themselves — a `/lecture` command, or
    a correction they already made — since there is then nothing to
    second-guess, and a correction deliberately carries none so the two
    answers can't ping-pong.
  - **Stop reaches the classify** (`routeCtrl`, aborted by `stopAsk`). A
    message stopped while it is still being routed has no turn yet, so
    `askCtrl` has nothing to abort — without its own controller the reader's
    Stop is silently ignored and the answer they cancelled starts a moment
    later.

  A lecture streams on the **same `askCtrl`** as an answer: both are replies to
  a typed message, so the next message supersedes whichever was in flight.
  Its scope is `selectLectureNodes` whether it was commanded or routed — the
  router decides which *agent* answers, not which papers, and rescoping
  because a lecture was asked for in words would make one request mean two
  things.
- **One Clear.** `clearConversation` (`chatCleared` + a fresh session id, plus
  the fold overrides that addressed the turns being cleared) is the bin in
  the composer. There were two from v7.10.0 to v7.21.0 — a `clearLecture` on
  the Lecture caret row beside it — because with two sections on screen a
  single button could not say which of the two it would wipe. With lectures in
  the transcript there is one thing to clear.
- **The composer holds the filters again** (Patrick, 2026-09-14). v7.11.0
  moved three controls *out* of the pill on the reasoning that a pill holding
  three controls and a textarea read as clutter — "the box you type in should
  look like a box you type in" — and that reasoning still stands for the
  📚 source scope, which sits as a chip in `.ask-tools` under the bar. But two
  of those three controls are gone since (the 🔍 toggle, replaced by `@` in
  v7.18.0; the 🎓 lecture scope, in v7.21.0), so ▽ Filters came back inside,
  next to the question it binds most directly. In the bar it wears the clear
  button's clothes rather than its own chip look — a 34px transparent circle —
  because `.bar-toggle`'s `--bg` pill reads as a dark hole against the
  composer's lighter surface, and because three controls in a row should look
  like one set. Its popover anchors to the bar and spans it, which is the same
  width the Chat row used to give it and the reason it is not anchored to the
  little funnel itself.

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
on. The panel's title row holds only the title and the ✕.

The **📚 source scope** is a chip in `.ask-tools`, the row directly beneath
the bar. It binds the *researcher* — what it may read and search when it
answers — and both a peer "Grounding" section and a slot in the panel header
would imply it scoped everything (Patrick's call). Beneath rather than above:
you read the question first, then what bounds it, and the row is far enough
from the text field to stop being chrome around it.

**▽ Filters is inside the bar** (Patrick, 2026-09-14) — see the bullet above
for why it came back and how it is dressed for the pill.

**The history of the pill is worth knowing before moving anything back into
it.** Four controls sat inside it until v7.11.0 (📚 scope, 🔍 direct search,
▽ filters, and the 🎓 lecture scope), which is what made it read as clutter:
the one thing you came here to use — a box to type in — looked like a toolbar
with a text field wedged in it. All four moved out, to one of two homes
depending on the panel's shape: the Chat section's caret row with a graph open,
`.ask-tools` without one. Since then the 🔍 toggle became `@` (v7.18.0, see
`../mentions/README.md`), the 🎓 scope went with the lecture slot (v7.21.0),
and the sections that provided the second home went too — leaving two
controls, one home each.

Every trigger is **its icon alone** when docked (the popover shows the truth
once open, an accent fill marks a narrowed scope, and the tooltip spells it
out); the landing tool row has width for labels, which is where a first-time
reader meets them. In the bar the label is hidden at every width — a word in
the pill is exactly the clutter v7.11.0 cleared out. Popovers open **upward**
from both homes now: the bar and the row beneath it both sit at the bottom of
the column, which is where the room is. The filter popover anchors to the bar
and spans it rather than to the funnel that opens it, because a popover the
width of a button has no room for a year slider.

The bar and the tool row are wrapped together in `.ask-dock`, which is what
the landing surface's FLIP measures — the two drop from the optical centre to
the bottom as one thing on the first question, and a row that snapped while
the bar slid would read as two unrelated controls.
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
  agent is composing* — the send button mid-answer, a bubble waiting on its
  first token. The shared `.spin` primitive
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
conversation fold, which of the two homes each ask-binding control (📚 scope,
▽ filters) renders in for each shape (including that none of them is inside
the bar), a set of **negative** assertions pinning that no lecture UI came
back (no Play button, no `Summary`/`History` pair, no framing group, no 🎓
scope), and the derived fold rule — the newest lecture open, the ones behind
it folded, and a reader's override on one turn leaving the others alone.
`test/teacher/transcript/ChatMessage.test.tsx` covers the turn itself: the
caret, the graph line's *conditional* appearance, and a lecture's own
grounding line. Browser-milestone items: a lecture lighting beats as they
stream, a
researcher answer with trace chips + an inline figure, the library chat with a
scope subset, Clear detaching follow-up context, and a save→restore round trip
rehydrating the whole conversation — including a pre-v7.21.0 save's lecture
arriving as a turn.


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


## What the lecture intro used to say (v7.7.0–v7.21.0)

`.lecture-intro` above the Lecture button carried a conditional sentence: when
papers on the graph hung off *another* paper rather than the seed, it named how
many. The sentence was **inverted in v7.17.0** — it used to say no lecture
covered them ("Re-seed on one to hear its story"), because each mode was
scoped to the seed's own neighbours and a satellite fell outside every one of
them; once a lecture narrated whatever was scoped, satellites WERE covered and
the sentence said so ("That includes the 3 papers you expanded"). Same count,
opposite claim, worth stating either way.

**The paragraph, the count and the selector behind it are all gone in
v7.21.0**, with the section that held them. `selectSatelliteCount` asked *is
this paper joined to the seed by an edge?* over the *grounding* nodes, so it
tracked what a lecture would actually cover right now; with nothing rendering
it, keeping it would have been a tested selector no caller reads.

Whether the panel should say this at all any more is a fair open question — a
reader who has been expanding the graph still benefits from knowing satellites
are included, and the command menu's one-line hint has no room for it. If it
comes back it belongs wherever the reader is told what `/lecture` covers, and
the selector is ten lines to re-derive from the seed's edges.
