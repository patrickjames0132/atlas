# `src/figures`

The full-screen figure lightbox — click anywhere (or the ✕, or Escape) to
close.

```
figures/
  Lightbox.tsx
```

## Why it's here, not nested in a feature folder

This is the frontend's first true multi-consumer component, so it lives at
the root per the hybrid structure rule (`src/README.md`): a component with
more than one render site gets its own folder; a single-parent one nests
inside whichever feature owns it.

It started in `teacher/figures/` (built for the agent's cited answer
figures — `AnswerFigure`s always carry a `figure` number and an `index`).
Once the detail panel's own paper figures (`detail/DetailPanel.tsx`) became
a second, unrelated caller, it was promoted here rather than either feature
importing from the other's folder — teacher's `FigCard.tsx` stayed put
(still teacher-only chat-bubble styling), only the shared lightbox moved.

## Design decisions worth knowing

- **One prop shape serves two very different callers.** `AnswerFigure`
  (`api/agents.ts`) has only `image`/`caption`/`title` required — `figure`,
  `index`, and `slot` are optional because the detail panel's paper figures
  have none of them (they're just a list in DOM order, not individually
  numbered/cited the way an agent's `show_figure` attachment is). The
  caption line renders `Figure N` only when `figure` is a number, and joins
  whatever combination of that/`title`/`caption` is actually present rather
  than assuming all three — an easy trap now that a second caller can leave
  most of them unset.
- **The detail panel passes `title: null`.** Showing the paper's own title
  in its own lightbox would be redundant — you're already looking at its
  detail panel. The teacher's answer figures need it (they can be for *any*
  cited paper, not just the one you're looking at).
- **Each caller owns its own lightbox state.** `Teacher.tsx` and
  `graph/GraphExplorer.tsx` each hold their own `useState<AnswerFigure |
  null>` and render their own `<Lightbox>` instance — this component has no
  state of its own beyond the Escape-key listener. Simpler than threading
  one shared instance through two unrelated component trees for a feature
  that's never open from both places at once anyway.

## Who uses it, and how/why

- **`teacher/Teacher.tsx`** — enlarges a cited paper's figure, attached via
  the researcher's `show_figure` tool and rendered inline in the chat
  (`teacher/figures/FigCard.tsx`'s click handler).
- **`graph/GraphExplorer.tsx`** — enlarges one of the selected paper's own
  figures (ar5iv), rendered in `detail/DetailPanel.tsx`.

## How it's verified

`tsc --noEmit` strict + oxlint; click-to-enlarge and Escape-to-close are
browser-milestone items.
