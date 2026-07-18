# `src/detail`

The selected paper: the right-hand detail panel and the selection state
behind it.

```
detail/
  useSelection.ts — selection id, lazy hydration/figures/code/categories, click gesture
  DetailPanel.tsx — the panel (badges, summary, category tags, actions, code links, figures)
  detail.css      — styles (ported light-touch)
```

Figures are click-to-enlarge via `../figures/Lightbox.tsx` — a root-level,
multi-consumer component (also used by the teacher's answer figures), not
nested here; see `figures/README.md`. `DetailPanel` takes an `onEnlarge`
callback rather than owning the lightbox itself — `GraphExplorer.tsx` (its
parent) holds that state, same pattern as `Teacher.tsx` does for its own
figures.

## Design decisions worth knowing

- **One summary section, abstract-first, TL;DR a click away.** The
  `SummarySection` (in-file, single-parent) shows the abstract by default
  with a tab to the TL;DR — S2's own when it exists; otherwise the tab
  wears a ✦ and the first click generates one via the backend's
  `summarizer` micro-agent (`onGenerateTldr` → `api.generateTldr` →
  `POST /api/paper/tldr`). **That click is the only surface that can
  trigger a Claude call** — Patrick's billing rule — and the server caches
  the result by node id forever, so each paper bills at most once; a
  cached summary rides ordinary hydration for free afterwards. Failure
  shows in place and the abstract stays a tab away.
- **Everything about a paper loads lazily, and each thing exactly once.**
  Graph neighbors arrive summary-light; opening one hydrates its
  abstract/TL;DR on first click (cached per paper). Figures (ar5iv) fetch
  on first open, with failures cached as `unavailable` so a flaky ar5iv
  isn't re-hit; code links (HF Papers) and category tags (arXiv's own
  metadata) each use a requested-set for the same guarantee. A new graph
  invalidates all four caches and selects its seed.
- **Hydration works for non-arXiv papers** (fixed in this port): the fetch
  uses `arxiv_id ?? id` — the old code's arXiv gate left journal papers
  abstract-less forever, the client half of the hydration bug fixed
  server-side in Phase 5. Figures, code links, and category tags stay
  arXiv-gated on purpose: ar5iv, HF Papers, and arXiv's own metadata are all
  arXiv-keyed — a journal paper's node just never requests them.
- **The click gesture:** single click selects; a quick (<350 ms) second
  click on the same node re-seeds the whole graph on it — wandering the
  literature node-to-node. Re-seeding uses the S2 paperId so journal
  papers work as seeds too.
- **`DetailPanel` is purely presentational**, and its `CodeRow`/
  `CodeSection`/`CategoryTags` children are single-parent — nested in the
  parent's file per the hybrid structure rule. The HF section caps rows
  (3 models / 2 datasets / 2 Spaces) with the totals linking out to HF
  Papers; the PDF link renders only for arXiv papers (it rewrites `/abs/` →
  `/pdf/`). Category tags render as read-only pills (unlike the search
  filter's clickable `.cat-chip` — nothing to toggle here) between the
  meta line and the TL;DR.

## Who uses it, and how/why (traced from the old app)

`graph/GraphExplorer.tsx` owns the `useSelection` instance, hands its
`onNodeClick` to `GraphCanvas`, renders `DetailPanel` when `selected` is
non-null (passing it `onEnlarge={setLightbox}` for its own lightbox
instance), and passes `selectedId` back to the canvas for the selection
ring. The teacher's "papers I cited" chips also drive `setSelectedId`.

## How it's verified

`tsc --noEmit` strict + oxlint; the lazy-load/caching behavior and the
double-click re-seed are browser-milestone items (click a journal paper —
its abstract should now appear).
