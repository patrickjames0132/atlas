# `src/ui`

Small cross-cutting UI utilities with multiple consumers and no feature
home — the root-level case of the hybrid structure rule. One module today:

```
ui/
  useResizablePanel.ts — drag-to-resize for a right-docked panel, width
                         remembered in localStorage
```

## `useResizablePanel`

Both the detail panel and the assistant panel dock on the right (border on
their left edge), so the drag handle lives on that inner-left edge:
dragging *left* widens, *right* narrows. The hook owns only the width
number + the pointer bookkeeping; the caller renders the panel with
`style={{ width }}` and drops a handle element wired to
`onHandlePointerDown`.

- **`defaultWidth` must match the panel's CSS width** so nothing shifts on
  first paint (the stored width, once one exists, wins).
- Each consumer passes its own `storageKey`, so the two panels remember
  their widths independently.
- Bounds clamp to 280–680px by default, overridable per panel.

## Who uses it

`detail/DetailPanel.tsx` and `teacher/Teacher.tsx` — the two right-docked
panels. (A second consumer is exactly why this lives at the root rather
than nested in either feature folder.)

## How it's verified

`tsc --noEmit` strict + oxlint; drag behavior and width persistence are
browser-milestone items.

## `theme.ts` — light/dark

A module-level store (not a context) behind `useSyncExternalStore`, because
its two consumers sit at opposite ends of the tree: the header's toggle
button and `graph/canvas/GraphCanvas`, which paints with JS and so can't
inherit a CSS variable from a stylesheet.

- **Dark is the default**, and deliberately *not* `prefers-color-scheme` —
  Atlas is a dark-first app, and a light OS setting shouldn't hand a
  first-time user the theme we treat as the alternative. Light is an
  explicit opt-in, remembered in `localStorage`.
- **The palette lives in CSS**, not here: dark on `:root`, light on
  `:root[data-theme='light']` (`index.css`). This module only stamps
  `data-theme`, so adding a themed color is a stylesheet edit.
- **The relation palette is intentionally theme-independent** — gold seed,
  blue references, green landmarks, pink search carry *meaning*, and read on
  either background. Only the neutrals flip.
- **The toggle's icon shows the action, not the state**: ☀ while dark
  (click for light), ☾ while light. A single toggle button labelled with its
  current state is the one people click twice; the `title`/`aria-label`
  spells it out either way.
