# `src/teacher/transcript`

Rendering the assistant's conversation: lecture beats and chat turns, with
Markdown + math + clickable citations. A single-parent cluster nested per
the hybrid structure rule — only `teacher/Teacher.tsx` renders the two
top-level components.

```
transcript/
  BeatList.tsx       — lecture beats (click to light their papers)
  ChatMessage.tsx    — one turn: retrieval line, trace chips, prose+figures
  AnswerMarkdown.tsx — Markdown + KaTeX + citation rendering for answers
  remarkCite.ts      — the remark plugin that turns [n]/[Sn] markers into chips
  provenance.ts      — the counts under an answer -> the one grounding line
```

## The pieces

- **`BeatList`** — each beat is a card: heading, prose, optionally one real
  paper figure (adapted to the `AnswerFigure` shape `FigCard` renders).
  Click a beat to light its papers on the graph; click the active one again
  to clear. Which beat is lit is panel-local UI state — only the resulting
  highlight ids are global (the store's highlight slice).
- **`ChatMessage`** — one turn end-to-end: the library-retrieval summary
  (graph-free mode), the researcher's live trace chips (reads / expansions
  / searches — a failed search explains *why* in plain words:
  `searchFailReason` maps the backend's `reason` codes), the prose
  interleaved with its `<<FIG n>>` figures (via `../figures/split`), and
  the cited-papers footer — clickable to re-light the answer's whole
  grounding set.
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

## Who uses it

`teacher/Teacher.tsx` renders `BeatList` and `ChatMessage`; the click
callbacks dispatch into the store's highlight slice. `AnswerMarkdown` and
`remarkCite` are internal to this cluster.

## How it's verified

`tsc --noEmit` strict + oxlint; beats lighting as they stream, trace chips,
and clickable `[n]` citations are standing browser-milestone items.
