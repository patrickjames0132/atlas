# `src/detail`

The selected paper: the right-hand detail panel and the selection state
behind it.

```
detail/
  useSelection.ts — selection id, lazy hydration/figures/code/categories, click gesture
  DetailPanel.tsx — the panel (badges, meta incl. the publication venue,
                    summary, category tags, actions, code links, figures)
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
  abstract/TL;DR on first click (cached per paper). Figures fetch on first
  open — keyed by `arxiv_id ?? id`, since a paper off arXiv gets its
  figures mined server-side from its open-access PDF — with failures cached
  as `unavailable` so a flaky upstream isn't re-hit; code links (HF Papers)
  and category tags (arXiv's own metadata) each use a requested-set for the
  same guarantee. A new graph invalidates all four caches and selects its
  seed.
- **The loadable sections reveal together, behind one joint gate.** While
  ANY of the node's fetches is in flight — summary hydration (reported by
  `useSelection`'s `detailLoading` id), arXiv tags, code links, figures —
  every loadable section holds its place with an anonymous shimmer block
  (`Skeleton`, in-file; `.skel-*` variants shaped like the content to
  come), *including one whose answer already landed*, and the whole set
  reveals in a single paint when the last answer arrives (Patrick's call:
  figures beating the abstract in read as jank; the first per-section
  version let each resolve independently). Empty sections simply don't
  appear at the reveal. The arXiv-keyed trio infers "in flight" from
  `arxiv_id && response === undefined` — those fetches always fire on
  first open and cache their failures, so undefined can only mean
  pending. Non-arXiv papers gate only on hydration: their figures fetch
  (OA-PDF mining, potentially a whole download) is deliberately OUTSIDE
  the joint gate, revealing when it lands rather than holding the panel
  hostage. The node-local parts (badges, title, meta, actions) render
  instantly — they never load, so they never pop. Skeletons are
  **headless on purpose**: a section may resolve to "nothing", and a named
  header that then vanishes would be its own jank. Purely decorative —
  `aria-hidden`, with the shimmer disabled under `prefers-reduced-motion`.
- **Hydration works for non-arXiv papers** (fixed in this port): the fetch
  uses `arxiv_id ?? id` — the old code's arXiv gate left journal papers
  abstract-less forever, the client half of the hydration bug fixed
  server-side in Phase 5. Figures now use the same `arxiv_id ?? id` key
  (the backend mines a journal paper's OA PDF). Code links and category
  tags stay arXiv-gated on purpose: HF Papers and arXiv's own metadata are
  arXiv-keyed — a journal paper's node just never requests them.
- **The click gesture:** single click selects; a quick (<350 ms) second
  click on the same node re-seeds the whole graph on it — wandering the
  literature node-to-node. Re-seeding uses the S2 paperId so journal
  papers work as seeds too.
- **`DetailPanel` is purely presentational**, and its `CodeRow`/
  `CodeSection`/`CategoryTags` children are single-parent — nested in the
  parent's file per the hybrid structure rule. The HF section caps rows
  (3 models / 2 datasets / 2 Spaces) with the totals linking out to HF
  Papers; the PDF link rewrites `/abs/` → `/pdf/` for arXiv papers, and for
  papers off arXiv it points at the hydrated `oa_pdf` URL (the same
  open-access PDF the backend mines for figures) — absent both, no link.
  Category tags render as read-only pills (unlike the search
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
