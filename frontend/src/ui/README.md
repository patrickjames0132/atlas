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
- Bounds clamp to 280–680px by default, overridable per panel — **and to 40%
  of the window** (`maxFraction`), see below.

### The width is capped by the window, the choice is not (v7.10.0)

A width in px alone is a promise the window cannot always keep. The panels
are `flex-shrink: 0`, so a panel dragged to 600px on a big monitor stayed
600px in a small window and the *canvas* gave instead — until the layout
overflowed and the page scrolled sideways (the docked chat's
sideways-scroll bug). So the ceiling is `min(max, maxFraction × innerWidth)`,
re-read on every `resize`, and `min` yields to it in a window too narrow to
honour both — a panel wider than its share of the screen is the thing being
prevented.

The reader's chosen width is stored **unclamped** and only the *rendered*
width is capped, so narrowing the window borrows width and widening it hands
the choice straight back. A drag is clamped as it moves, so the handle can
never run away from the edge you are dragging.

## Who uses it

`detail/DetailPanel.tsx` and `teacher/Teacher.tsx` — the two right-docked
panels. (A second consumer is exactly why this lives at the root rather
than nested in either feature folder.)

## How it's verified

`tsc --noEmit` strict + oxlint, plus `test/ui/useResizablePanel.test.tsx` —
width seeding, drag direction, the px bounds, the pointer-up persist, and the
viewport cap (including that a widened window returns the stored choice). The
feel of a live drag stays a browser-milestone item.

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


## `useResizablePanel` docks either way (v7.8.0)

It was written for right-docked panels (the detail panel, the assistant), where
dragging the inner-left handle *leftward* widens. The left rail is the exact
mirror, so the hook gained a `side` option rather than a twin: it flips the
sign of the drag and nothing else. Both directions keep the same feel — the
pointer moves *away* from the panel's own edge to widen it, which is the only
property that has to hold.
