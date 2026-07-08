# `src` — the Atlas frontend

React + TypeScript (strict) + Vite. State follows one rule: **a component's
state lives where the component lives; only genuinely cross-cutting state
goes to the Redux store** (`store/` — three slices: workspace, transcript,
highlight). Structure follows the hybrid rule: feature folders at the root
for anything with multiple consumers or render sites; single-parent
components nest inside their parent's folder (e.g. `teacher/transcript/`).

## The render-tree map (find a component by where you see it)

```
<Atlas>                            Atlas.tsx        — the shell
├─ header bar                      header/AtlasHeader.tsx
│  ├─ brand ("Atlas" — click = Home: clears the workspace)
│  ├─ search box + filter popover  search/Search.tsx (year slider, field picker)
│  ├─ seed title · drawer toggles  (📚 Sources · 🎓 Assistant · 🗂 Sessions)
│  └─ "Powered by Claude" credit
├─ Sources drawer (📚)             library/Sources.tsx
├─ Sessions drawer (🗂)            sessions/Sessions.tsx
└─ body
   ├─ graph area                   graph/GraphExplorer.tsx
   │  ├─ overlays (from the shell): hit list  search/HitList.tsx
   │  │                             loading / error / hint  (Atlas.tsx)
   │  ├─ controls panel            graph/GraphControls.tsx
   │  ├─ the canvas                graph/GraphCanvas.tsx
   │  ├─ legend                    graph/Legend.tsx
   │  ├─ detail panel (on select)  detail/DetailPanel.tsx
   │  └─ figure lightbox           figures/Lightbox.tsx
   └─ assistant panel (🎓)         teacher/Teacher.tsx
      ├─ scope picker              teacher/ScopePicker.tsx
      ├─ lecture beats             teacher/transcript/BeatList.tsx
      ├─ chat turns                teacher/transcript/ChatMessage.tsx
      │  └─ inline figures         teacher/figures/FigCard.tsx
      └─ figure lightbox           figures/Lightbox.tsx (same instance type as above,
                                    but GraphExplorer and Teacher each own their own)
```

`figures/Lightbox.tsx` is the frontend's first true multi-consumer, root-level
component (promoted from `teacher/figures/` once the detail panel became a
second caller) — see "the hybrid rule" above.

Non-visual folders: `api/` (the typed backend client — the only layer that
knows URLs and SSE frames), `store/` (the three slices + typed hooks),
`notation/` (the cross-cutting math renderer — `<MathText>` for the DOM
surfaces, `latexToUnicode` for canvas node labels), `graph/hooks/` +
`graph/model.ts`/`theme.ts` (the sim machinery), `search/useSeedSearch.ts`,
`detail/useSelection.ts`, `teacher/useConversation.ts` (each feature's
state/logic hooks).

Every folder has its own README with the full story — this file is just the
map. Verified by `npm run build` (strict tsc + Vite) and oxlint; behavior
by the end-of-phase browser milestone.
