# `src/tour` — the guided coach-mark tour

A stepped, spotlight-style product tour (the Yotpo pattern): dim the screen,
ring one control at a time, explain it in an anchored bubble with Back / Next,
a step counter, a **jump select** worn by the bubble's title (the heading
highlights on hover; click it and pick any stop's numbered title to skip
straight there instead of Next-ing through the walk — a transparent native
`<select>` stretched over the h4, so the browser's own dropdown does the
work), **Skip tips**, and a ✕. First motivation: the node-selector's
alt-drag / shift-click / alt-click gestures, which are otherwise discoverable
only through the controls' one-line hint.

```
tour/
  Tour.tsx  — the generic overlay: resolves targets, spotlights, positions
              the bubble, walks the steps (arrow keys / Esc wired)
  steps.ts  — HOME_TOUR (the search surface) + GRAPH_TOUR (the graph tools),
              and TOUR_KEYS, one seen-flag per phase
  tour.css  — backdrop (z 60) < spotlight (61) < bubble (62); the dimming is
              the spotlight's 200vmax box-shadow, so there's exactly one hole
```

## Two phases

The app has two first-times, so the tour has two phases, each with its own
localStorage seen-flag: **HOME_TOUR** (the search box, its filter popover, the
data-source dropdown, and the three header drawers — Library, Assistant,
Sessions) auto-runs on first launch, before any graph exists; **GRAPH_TOUR**
(the graph tools, the detail panel, the lectures, the Q&A researcher)
auto-runs when the first graph lands. `Atlas.tsx` picks the list by whether a
graph is up — the same "?" click tours whatever the user is actually looking
at. Swapping the `steps` prop mid-run restarts the walk from the new list's
first stop.

## Staged steps — the tour opens panels

A step may carry `stage: '<name>'`: on entering it, `Tour` calls the caller's
`onStage(name)` and then **polls briefly for the target** (a just-opened
drawer needs a beat to mount) before spotlighting it — so the Library /
Assistant / Sessions steps open their own panel and the walk continues
inside it. Entering a step with no stage fires `onStage(undefined)`, which is
the caller's cue to put drawers away again (in `Atlas`, the two drawers close;
the assistant only ever opens — collapsing it mid-walk would hide the graph
tour's own lecture/ask stops, which stage it too). A staged step's target may
not exist (or be visible) at mount, so its walk-membership is judged by
`presentIf` — an **existence** check, not a visibility one, because it gates
on the *data condition* (the lecture-scope picker only renders once a lecture
has been played; the ✕-able panel steps probe their toggle button) while the
staging is what makes the element visible when reached. A staged step with no
`presentIf` is assumed stageable. A staged target that never shows within the
polling window drops its stop and the walk moves on — so conditional UI like
the scope pickers simply joins the tour once it exists, and a "?" re-run
teaches more as the panel grows.

## The contract

`Tour` is data-driven and dumb: a `steps` array of
`{ target, title, body }` where `target` is a CSS selector, plus one
`onClose(completed)` callback. **Mounting starts the tour**; the caller owns
open/closed state and what "seen" means. Steps whose selector matches nothing
— or matches a hidden element (`checkVisibility`, so a collapsed panel's
children skip too) — are dropped at mount, and the counter reflects only real
stops, so one list describes the *maximal* tour: the year/citation sliders
only render on graphs that span a range, the lecture grid needs the assistant
panel open, and none of that needs step-list logic.

Targets are marked with `data-tour="…"` attributes where the controls render
(`search/Search.tsx`, `graph/controls/GraphControls.tsx`,
`detail/DetailPanel.tsx`, `teacher/Teacher.tsx`) rather than by reusing style
classes — a rename-safe, greppable contract between `steps.ts` and the DOM.

## Who drives it

`Atlas.tsx`: auto-runs each phase **once ever** (guarded by its
`TOUR_KEYS` localStorage flag) — home on first launch, graph on the first
graph — and re-launches the current phase from the header's always-present
**"?"** button (`.tour-launch`). Done, Skip, ✕, and Esc all mark the phase
seen — the auto-run never nags twice; re-runs are a deliberate click.

## Placement

The bubble prefers the target's right (the controls live top-left), falls back
to the left, then below, and always clamps into the viewport; the spotlight
re-measures on window resize and (capture-phase) scroll. If a step's target
disappears mid-tour — its panel was closed under the spotlight — the stop is
dropped rather than pointing at nothing.

## How it's verified

`test/tour/Tour.test.tsx` (jsdom/RTL): absent-target skipping and the honest
counter, Back/Next/Done walking, the jump select, all three quit paths,
arrow-key navigation, and the no-targets-at-all immediate close. Pixel placement and the spotlight
look are browser-pass items.
