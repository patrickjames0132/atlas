# `src/teacher/transcript`

Rendering the assistant's conversation: chat turns, the lecture beats some of
them hold, Markdown + math + clickable citations. A single-parent cluster
nested per the hybrid structure rule — only `teacher/Teacher.tsx` renders
`ChatMessage`, and only `ChatMessage` renders `BeatList` (it had a second
caller until v7.21.0 — the panel's Lecture section).

```
transcript/
  BeatList.tsx       — lecture beats (click to light their papers)
  ChatMessage.tsx    — one turn: retrieval line, trace chips, prose+figures,
                       or a lecture's beats + the route line
  AnswerMarkdown.tsx — Markdown + KaTeX + citation rendering for answers
  remarkCite.ts      — the remark plugin that turns [n]/[Sn] markers into chips
  provenance.ts      — the counts under an answer -> the one grounding line
                       (a lecture's comes from its scope instead — see below)
```

## The pieces

- **`BeatList`** — each beat is a card: heading, prose, optionally one real
  paper figure (adapted to the `AnswerFigure` shape `FigCard` renders).
  Click a beat to light its papers on the graph; click the active one again
  to clear. Which beat is lit is panel-local UI state — only the resulting
  highlight ids are global (the store's highlight slice).

  **Rendered in exactly one place since v7.21.0**: inside a `ChatMessage`
  whose answer is a lecture. It had a second home — the panel's Lecture
  section — from v7.20.0, when a routed lecture first landed on a turn, until
  the section was deleted. Worth knowing because of what the two homes left
  behind: a lit beat is addressed by **turn + index** (`activeChatBeat`), not
  by index alone, since a conversation can hold several lectures and an index
  would light a beat of the wrong one. The section's single lecture was the
  case an index sufficed for.
- **`ChatMessage`** — one turn end-to-end: the library-retrieval summary
  (graph-free mode), the researcher's live trace chips (reads / expansions
  / searches — a failed search explains *why* in plain words:
  `searchFailReason` maps the backend's `reason` codes), the prose
  interleaved with its `<<FIG n>>` figures (via `../figures/split`), and
  the cited-papers footer — clickable to re-light the answer's whole
  grounding set.

  A turn whose answer is a **lecture** (`message.beats`) renders a
  `BeatList` where the prose would be, behind its own **caret**
  (`.beats-toggle`, naming the beat count), and under a `.chat-routed` line
  naming the assistant that answered and offering the other when a model chose
  it. Details that are easy to get wrong and are pinned by tests: beats must
  suppress the "Thinking" dots (a lecture turn's `text` stays empty, which is
  exactly what the dots key off, so without this every lecture streams under a
  placeholder that never resolves); the beat click, the caret and the reroute
  button all `stopPropagation`, since the bubble's own handler would otherwise
  replace a beat's highlight with the turn's whole grounding set; the route
  line appears whenever `routedTo` is set even when the offer itself is
  withheld — the turn still has to account for what happened to it; and
  `beatsOpen` **defaults to open**, so a caller that forgets to manage it shows
  the lecture rather than silently hiding it. Folded beats are `hidden`, not
  unmounted, so their figures stay loaded and unfolding is instant.

  **Which turn is open is the caller's call, not this component's** — the rule
  is "the newest lecture, until the reader says otherwise", and that is a fact
  about the whole conversation. `Teacher.tsx` derives it and holds the reader's
  overrides; see its README.

- **A turn says which graph it came from, but only when that matters.**
  `message.graph` (the seed's id and title plus the papers in scope) is stamped
  on every turn at turn start, and `.chat-graph` renders *"From the “…” graph"*
  **only when `currentSeedId` differs from it**. That condition is the whole
  design. The app already degrades correctly when a conversation outlives its
  graph — stale `[n]` chips grey out, the bubble stops being clickable — but
  every one of those signals is negative: they say *this points nowhere any
  more* and never *this was about the Attention graph*. The line is the
  positive half, and it appears exactly where a reader would otherwise be
  confused. When the graph matches, they are looking at it, and a line
  repeating its title under every turn is noise.

  It sits **above** the content rather than in the footer: a reader scrolling
  back needs it before they wonder why clicking a citation does nothing.

- **A lecture gets its own grounding line.** An answer's footer comes from
  `provenance`, which counts what the backend watched itself do — and a lecture
  makes no tool calls, so it has none and used to carry no footer at all. Its
  line comes from `message.graph.nodes` instead: *"narrated 14 papers"*, in the
  same `.chat-cited` class, because what a lecture covered is the honest
  equivalent of what an answer cited and the two should read alike.
- **`AnswerMarkdown`** — the researcher replies in Markdown
  with `$…$` math and inline citations; this renders all three for
  real: remark-gfm for structure, remark-math + rehype-katex for math (the
  same KaTeX the rest of the app reaches through `MathText` — beats, the
  detail panel, and search hits keep `MathText`; only answers get the
  fuller Markdown treatment), and `remarkCite` for the markers. Links
  always open a new tab — an answer lives in a docked panel.
- **`remarkCite`** — rewrites citation markers into synthetic elements the
  renderer maps to chips. Two flavors, matched in one alternation so neither
  can swallow the other: `[n]` → `citeref` (a graph paper) and `[S2, p.460]`
  → `sourceref` (a passage from the user's own library). It only rewrites the
  *shape*; whether a marker resolves is decided at render time — `[n]` from
  the answer's `graphRefs` map (clickable, spotlighting that node), `[Sn]` from
  its `sourceRefs` map (rendered as the source's real title and page, the
  page read off the marker itself). Either kind degrades to its raw text when
  unresolvable — never broken. With **no graph** to spotlight, `[n]` falls
  through to the answer's `paperRefs` map and becomes a button that *builds*
  that paper's graph (`onPaperSeed`) — what makes a graph-free survey a way
  *into* the graph rather than a list of outbound links. It stays the bare
  `[n]` the prose was written around (rendering full titles inline derailed
  the sentence, twice over when two papers back one claim) with the title on
  hover, and carries a small node-and-edge glyph.

  **The seed click builds under the citation's own provider**, not the
  dropdown's. A `PaperRef` carries the backend that minted its `node_id`
  (since v6.14.0), because that id resolves nowhere else: switch the Data
  source mid-conversation, or restore a session saved under the other
  backend, and building with the selected provider looks the id up in a
  namespace it was never in — the graph just fails to build. Following the
  ref instead takes the workspace to that backend, which is the honest
  outcome (the graph on screen really is from there, and every expand off it
  follows), so the chip's tooltip names the switch *before* the click rather
  than letting the dropdown change under the reader. Refs from before v6.14.0
  carry no provider and fall back to the selected one — the old behaviour.

  **The glyphs are not decoration.** After a chat→graph jump one transcript
  holds both kinds of chip, and they do different things — a spotlight is a
  reversible highlight, a seed rebuilds the workspace — so a reader must be
  able to tell them apart *before* clicking. They're a matched pair in one
  visual language, differing exactly where the behaviour does: **three nodes
  wired together** (teal) builds a graph, **one node lit** (accent blue)
  lights up a paper already on one. Marked in shape as well as colour on
  purpose — colour alone says *that* they differ without saying *what*, and
  says nothing at all to a colour-blind reader.

  **A third state, from the same cause.** Because a transcript now
  outlives the graph it was written against, an older answer can cite a
  paper that is no longer loaded — the marker resolved fine when it was
  written, but clicking would highlight nothing. Those chips render
  **greyed and inert**, checked per-chip against `selectWorkspaceNodeIds`
  (the loaded set, *not* the visible one — keying on the year/citation
  filters would flicker chips as a slider is dragged). They come back to
  life by themselves if that paper appears on a later graph.

  All of this runs on mdast text nodes only, so markers inside inline code
  or math are left untouched.

  Why the two resolve differently: the frontend already holds the numbered
  paper list, so it can resolve `[n]` itself; only the *backend* knows which
  library sources a turn retrieved, so `[Sn]` arrives pre-resolved on the
  stream (see `agents/README.md`).

- **`provenance`** — the grounding line under each answer. The backend ships
  *counts* (library searches, paper searches, passages, what the prose cites),
  never a verdict, so the wording lives here and can change without touching
  the agent. The rule it encodes: say what the answer drew on, and never imply
  grounding that isn't there — an answer that cited nothing says so, and
  "searched your library (no matches)" reads differently from "nothing was
  searched", because those are different things to tell a student. A
  conversational turn renders no line: a greeting asserts nothing, so
  attributing it would be noise.

## The trace, and answers that never arrive

- **The tool trace collapses itself.** Watching the agent work is the
  interesting part *while it works*; once the answer is there the trace is a
  wall of chips above the thing the reader came for. `TraceBlock` opens on its
  own when a run starts and folds to a one-line summary (`3 steps`) when it
  ends. **A reader's own click wins from then on** — the automatic collapse
  stops fighting them for the rest of that turn, because the point of an
  affordance is to be in control of it.
- **A failed answer says so on the turn itself**, not in panel state. The
  commonest failure by far is a run the reader *left* — closed the tab, or the
  page died mid-answer — so a message living in component state would be gone
  by the time they came back to look. It is written in two places for that
  reason: by the stream when it ends without prose, and by the **save** for
  the case where the client never reached the end of the run at all (see
  `settleInFlight`, which is the pagehide flush).
- **Try again re-runs the question, with the conversation behind it.** The
  failed exchange is dropped first, so the transcript keeps one exchange
  rather than a graveyard of attempts. The turns still on screen are sent with
  the request and used **only if the server has none of its own**: its history
  is in memory keyed by an id a reload discards, which is exactly the state a
  retry is usually in. A failed turn was never written to that history (it is
  recorded on success only), so what is sent is precisely the conversation up
  to the question being retried.

## Who uses it

`teacher/Teacher.tsx` renders `BeatList` and `ChatMessage`; the click
callbacks dispatch into the store's highlight slice. `AnswerMarkdown` and
`remarkCite` are internal to this cluster.

## How it's verified

`tsc --noEmit` strict + oxlint, plus `test/teacher/transcript/` — where
`ChatMessage.test.tsx` covers the routed turn, and most of its weight is on
the *correction affordance*, since one-click correction is what makes routing
by model affordable in the first place. Beats lighting as they stream, trace
chips, and clickable `[n]` citations are standing browser-milestone items.
