# `src/notation`

Render the math notation in paper text so `$\beta_2$` shows as **β₂**, not raw
LaTeX source. Every paper-text surface — abstracts, TL;DRs, titles, lecture
beats, chat answers, search hits, figure captions — feeds its strings through
here.

```
notation/
  MathText.tsx        the DOM surface: KaTeX-typeset <MathText> component
  splitMath.ts        tokenise text into plain / math runs (the shared parser)
  latexToUnicode.ts   the canvas surface: best-effort LaTeX → Unicode
```

## Why it's called `notation`, not `math`

It doesn't *compute* anything — no arithmetic, no vector helpers, which is what
a `math/` folder conventionally holds. It **renders notation** for display. The
name also matches the roadmap item it ships ("Proper subscripts & math
notation"). It's a cross-cutting utility with many consumers, so it lives at the
root per the hybrid structure rule (`src/README.md`), like `figures/`.

## The two surfaces, and why they differ

The same paper title reaches the user through two rendering technologies, so
there are two entry points sharing one parser:

- **HTML → KaTeX** (`MathText`). Anywhere text lands in the DOM, `<MathText>`
  splits it and hands each math run to KaTeX, which emits real typeset markup
  (with MathML for accessibility). This is the good path — proper fractions,
  superscripts, symbols.
- **Canvas → Unicode** (`latexToUnicode`). Graph node labels are painted with
  `ctx.fillText` (`graph/GraphCanvas.tsx`), where HTML/KaTeX can't reach. There's
  no way to typeset on a canvas, so this is a deliberate *approximation*: strip
  the delimiters, map Greek letters and simple sub/superscripts to their Unicode
  glyphs (β, ₂, ²), and leave anything unmappable as readable source. The goal is
  only that a label reads "β₂-VAE" instead of showing a stray `$`.

## Design decisions worth knowing

- **Delimited LaTeX only — no plain-text heuristics.** We render `$…$`,
  `$$…$$`, `\(…\)`, `\[…\]` and nothing else. Bare "CO2" / "H2O" in an abstract
  is left untouched on purpose: auto-subscripting a digit after a letter misfires
  on "GPT4", "COVID19", "Section 2" far too often to be worth the few true hits.
- **The inline `$…$` boundary rule is the whole ballgame.** Prose says "costs
  $5 and $10", and that must *not* render as math. `splitMath` uses the CommonMark
  math-extension rule: an opening `$` can't be followed by whitespace, a closing
  `$` can't be preceded by whitespace nor immediately followed by a digit.
  Currency fails all three and falls back to text. `$$…$$` is checked before
  `$…$` so display math wins the longer match.
- **Unterminated delimiters fall back to text, never throw.** Chat answers
  stream token-by-token, so mid-stream you'll see a half-typed `$\bet` with no
  closer — that renders as plain text until the closing `$` arrives, so nothing
  flickers or crashes as the buffer grows.
- **KaTeX runs with `throwOnError: false`.** Malformed LaTeX degrades to a
  red-rendered source string instead of taking down the surface it's on. Paper
  abstracts contain plenty of LaTeX KaTeX can't parse; none of it should blank a
  panel.
- **`latexToUnicode` maps a sub/superscript group all-or-nothing.** `_{max}`
  can't become a subscript ('m' has no Unicode glyph), so it falls back to plain
  "max" rather than a half-converted "mₐₓ" — but symbol conversion runs *first*,
  so `\sigma_{max}` still yields "σmax", not a mangled control word.

## Who uses it, and how/why

`<MathText>` (HTML): `detail/DetailPanel.tsx` (title, abstract, TL;DR, and its
own paper figures' captions), `teacher/transcript/BeatList.tsx` (beat heading +
text), `teacher/transcript/ChatMessage.tsx` (answer prose),
`search/HitList.tsx` (hit titles — both the cache and live-Semantic-Scholar
lists), `teacher/figures/FigCard.tsx` + `figures/Lightbox.tsx` (figure title +
caption). Every figure-caption render path is covered — the detail panel's
inline captions, the teacher's inline `FigCard`, and the shared enlarged
`Lightbox`.

`latexToUnicode` (canvas): `graph/GraphCanvas.tsx` (node labels + the hover
tooltip string).

Deliberately *not* wired up: user-uploaded source titles
(`library/Sources.tsx`, `teacher/ScopePicker.tsx`) — filenames/URLs, not paper
math — and the researcher trace chips — truncated debug labels, not a reading
surface.

## How it's verified

`tsc --noEmit` strict + oxlint. The parser (`splitMath`) and the canvas
converter (`latexToUnicode`) are pure functions checked headlessly against the
tricky cases (currency, unterminated runs, unmappable subscripts); the KaTeX
rendering itself is a browser-milestone item.
