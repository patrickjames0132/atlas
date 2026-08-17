# `src` — the Atlas frontend

React + TypeScript (strict) + Vite. State follows one rule: **a component's
state lives where the component lives; only genuinely cross-cutting state
goes to the Redux store** (`store/` — four slices: workspace, transcript,
highlight, library). Structure follows the hybrid rule: feature folders at the root
for anything with multiple consumers or render sites; single-parent
components nest inside their parent's folder (e.g. `teacher/transcript/`).

## The render-tree map (find a component by where you see it)

```
<Atlas>                            Atlas.tsx        — the shell
├─ left rail (collapsible)         shell/SideBar.tsx
│  ├─ brand row (the whole row collapses the rail): "Atlas" · seed title
│  ├─ ✎ New graph
│  ├─ saved graphs (⋮ → rename / delete)   shell/useSessions.ts
│  └─ data source · ＋ Save · 📚 Library · ⚙ Settings · theme · ? tour
│                                   — the header died here in v7.8.0; the
│                                   search box had already left in v7.6.0, so
│                                   the chat bar is the app's only text input
├─ Library (a main-pane VIEW)      library/Sources.tsx (variant="pane")
├─ Settings modal (⚙)             settings/SettingsModal.tsx (config-file editor)
├─ guided tour overlay (?)         tour/Tour.tsx (two phases in tour/steps.ts —
│                                   search on first launch, graph tools on the
│                                   first graph; each auto-runs once)
└─ body                            two states: with no graph the assistant IS
   │                                 the body (a centred landing chat) and the
   │                                 overlays get their own layer; with a graph
   │                                 the explorer takes it and the assistant
   │                                 docks. Teacher stays at one position in the
   │                                 tree across both, so the switch never
   │                                 remounts it — see teacher/README.md.
   ├─ graph area                   graph/GraphExplorer.tsx
   │  ├─ overlays (from the shell): loading / error  (Atlas.tsx)
   │  ├─ controls panel (folded)   graph/controls/GraphControls.tsx
   │  ├─ find control (🔍 → pill)  graph/controls/FindBar.tsx
   │  ├─ the canvas                graph/canvas/GraphCanvas.tsx
   │  ├─ legend                    graph/controls/Legend.tsx
   │  ├─ detail panel (on select)  detail/DetailPanel.tsx
   │  └─ figure lightbox           figures/Lightbox.tsx
   └─ assistant (🎓)               teacher/Teacher.tsx — landing or docked;
      │                             docked it stacks two folding sections
      ├─ Lectures section          the four buttons + the shown lecture
      │  └─ lecture beats          teacher/transcript/BeatList.tsx
      ├─ Chat section              the conversation
      │  ├─ scope pickers          teacher/ScopePicker.tsx (🎓 + 📚, on the
      │  │                          Chat row — they scope the researcher)
      │  ├─ search controls        search/SearchControls.tsx (🔍 "Find papers"
      │  │                          + ▽ Filters — year slider, field picker;
      │  │                          same row, same ask they bind)
      │  └─ chat turns             teacher/transcript/ChatMessage.tsx
      │     └─ inline figures      teacher/figures/FigCard.tsx
      ├─ ask bar                    the question and nothing else (v7.11.0)
      │  └─ tool row               with no graph there is no Chat row, so all
      │                             four controls above sit as chips directly
      │                             under the bar (`.ask-tools`)
      ├─ "working" dots            teacher/HopDots.tsx (lecture button, send
      │                             control, and a bubble awaiting its first token)
      └─ figure lightbox           figures/Lightbox.tsx (same instance type as above,
                                    but GraphExplorer and Teacher each own their own)
```

`figures/Lightbox.tsx` is the frontend's first true multi-consumer, root-level
component (promoted from `teacher/figures/` once the detail panel became a
second caller) — see "the hybrid rule" above.

Non-visual folders: `api/` (the typed backend client — the only layer that
knows URLs and SSE frames), `store/` (the four slices + typed hooks),
`notation/` (the cross-cutting math renderer — `<MathText>` for the DOM
surfaces, `latexToUnicode` for canvas node labels), `graph/hooks/` +
`graph/model.ts`/`theme.ts` (the sim machinery), `ui/` (cross-cutting UI
utilities — `useResizablePanel` for both right-docked panels),
`search/useDirectSearch.ts`, `shell/useSessions.ts`, `detail/useSelection.ts`,
`teacher/useConversation.ts` (each feature's state/logic hooks).

Every folder has its own README with the full story — this file is just the
map. Verified by `npm run build` (strict tsc + Vite) and oxlint; behavior
by the end-of-phase browser milestone.

One oxlint rule is worth calling out because it encodes a house convention
rather than a correctness check: **`id-length`** (`min: 2`) is the frontend
half of CLAUDE.md's no-single-letter-identifiers rule — the backend half is
`bin/check_identifiers.py`. It runs over `src/` and `test/` alike. Two
deliberate settings:

- **`properties: "never"`** — object-literal keys and member access are
  exempt, because those names are usually not ours: react-force-graph's
  `node.x`/`.y`, a `VLink`'s `_s`/`_t`, react-markdown's `a:` component
  override, `latexToUnicode`'s subscript map keyed by the LaTeX character
  itself. The cost is that a destructured `const { a } = obj` slips
  through — an accepted trade for not drowning in false positives.
- **`exceptions: ["_"]`** — the pure-discard idiom, `.map((_, index) => …)`.

TypeScript property *signatures* are still checked (they're declarations, not
accesses), so the handful of genuinely external field names declared in our
own types carry a scoped `oxlint-disable` with a comment saying whose name it
is — see `graph/model.ts` (`x`/`y`) and `api/search.ts` (the `q` wire key).
