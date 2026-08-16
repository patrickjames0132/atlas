# `frontend/test`

The frontend test suite: **Vitest** (+ React Testing Library for the DOM
cases), mirroring `src/` the way the backend's `test/` mirrors `src/atlas/` —
a test lives in the folder matching the module under test.

```
test/
  detail/
    DetailPanel.test.tsx      — the joint loading gate: one skeleton set, one
                                reveal, once every fetch has answered
    SummarySection.test.tsx   — abstract-first with a TL;DR tab; ✦ generates
                                on the first toggle only
    useSelection.test.tsx     — a new graph opens onto the graph: selection
                                starts null and clears on every re-seed
  graph/
    model.test.ts             — formatPubDate/primaryRel/nodeRadius/cleanNode/
                                countRels/ID_RE (the pure view-model helpers)
    buildShape.test.ts        — the persisted graph shape + its corrupt-blob
                                fallbacks
    clusterForce.test.ts      — the Force layout's relation sectors and orbits
    controls/Legend.test.tsx  — the legend's conditional agent entries
    controls/FindBar.test.tsx — the collapsible find control's open/pin/clear
    controls/GraphControls.test.tsx — the action row, the shared readout, and
                                the panel's folded-by-default bar
    hooks/useDiscovery.test.tsx — a discovery's `_origin` anchor tracking
    hooks/useEscapeClear.test.tsx — Esc clears, except while typing
    hooks/useMarquee.test.tsx — the alt-drag marquee's hit-testing
    hooks/useTimeline.test.tsx — year + month fraction x-placement
  notation/
    splitMath.test.ts         — math vs. currency vs. mid-stream tolerance
    latexToUnicode.test.ts    — the canvas-label LaTeX approximation
    prepareMath.test.ts       — money is not math: what remark-math is
                                allowed to see
  settings/
    SettingsModal.test.tsx    — draft/dirty/save-error, search, the config
                                -file switch
  store/
    library.test.ts           — one shared copy of the uploaded sources
    transcript.test.ts        — the per-mode lecture cache's show/hide/drop
    workspace.test.ts         — hand-picked selection + grounding scope
  teacher/
    Teacher.test.tsx          — the panel's folding sections: the defaults,
                                the carets, tour staging, and which of its two
                                homes the 📚 source picker renders in
    HopDots.test.tsx          — the shared indicator's accessibility contract
    ScopePicker.test.tsx      — the controlled open/close contract (popover
                                only when `open`; trigger and ✕ report via
                                `onOpenChange`)
    figures/split.test.ts     — the <<FIG n>> interleaver's edge cases
    transcript/remarkCite.test.ts — [n] markers → citeref nodes, on mdast
    transcript/AnswerMarkdown.test.tsx — clickable `[n]` chips, end to end
    transcript/provenance.test.ts — the grounding line's honest cases
  tour/
    Tour.test.tsx             — step walking, absent-target skipping, the
                                three ways out
  ui/
    useResizablePanel.test.tsx — width seeding, drag direction, clamping, the
                                 viewport cap, the pointer-up persist
    theme.test.ts             — what the theme store defaults to, persists,
                                and stamps on the document
```

## The discipline (the backend's, mirrored)

- **Fully offline** — no live backend, no network. Everything covered so far
  is pure logic or self-contained DOM; when API-touching code gets tests,
  its `fetch`/SSE layer gets stubbed, never called.
- **Environment: node by default, jsdom by opt-in.** Config lives in
  `vite.config.ts`'s `test` block (`test/**/*.test.{ts,tsx}`). Pure-logic
  tests run in node; component/hook tests declare
  `// @vitest-environment jsdom` as their first line (all the RTL files do).
- **No globals** — `describe`/`it`/`expect` are imported from `vitest`
  explicitly, so the tests type-check without ambient type wiring.

## Running

- `npm test --prefix frontend` — one-shot (`vitest run`); what the gate runs.
- `npm run test:watch --prefix frontend` — watch mode while developing.
- `uv run nox -s vitest` — the same one-shot, as part of the repo-wide gate
  (`uv run nox` runs it after the backend tests; it skips cleanly when npm
  isn't on PATH, the Trivy pattern).

## What deliberately isn't tested (yet)

The force-graph canvas and the sim hooks (`graph/hooks/`) — their behavior
is mutation-heavy and visual (pins surviving filters, discoveries settling
near anchors), which the end-of-phase browser milestone exercises by hand;
jsdom has no canvas. The streaming teacher pipeline (`useConversation`) is
the next natural target: its SSE handlers can be driven with scripted
events, the same idea as the backend's `fake_claude`.
