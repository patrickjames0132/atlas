/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The tour step lists: data only — the walking/spotlighting lives in
 * `Tour.tsx`; the `data-tour` attributes these selectors point at are planted
 * where each control renders (`search/Search.tsx`,
 * `graph/controls/GraphControls.tsx`, `detail/DetailPanel.tsx`,
 * `teacher/Teacher.tsx`).
 *
 * Two phases, because the app has two first-times: {@link HOME_TOUR} covers
 * the search surface and auto-runs on first launch, before any graph exists;
 * {@link GRAPH_TOUR} covers the graph tools and auto-runs on the first graph.
 * `Atlas.tsx` picks the list (and the seen-flag) by whether a graph is up.
 * Within a list, steps whose control isn't on screen skip themselves (the
 * year/citation sliders only render when the graph spans a range, the detail
 * panel needs a selected paper, the ask bar needs the assistant open),
 * so each list describes its phase's *maximal* tour.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { TourStep } from './Tour'

/** localStorage keys remembering each tour phase has auto-run once. */
export const TOUR_KEYS = {
  /** The pre-graph search tour — first launch. */
  home: 'atlas.tour.home',
  /** The graph-tools tour — first graph. */
  graph: 'atlas.tour.graph',
} as const

/** The startup tour: the chat bar, before any graph is loaded. */
export const HOME_TOUR: TourStep[] = [
  {
    target: '[data-tour="ask"]',
    title: 'Start here',
    body:
      'One box for everything. Ask a research question and the assistant goes looking — ' +
      'through the literature, and through your own uploaded sources if you have any. ' +
      'Or paste an arXiv id or URL to jump straight to that paper’s map. No graph or ' +
      'library needed to begin; just saying hello stays a conversation.',
  },
  {
    // Anchored to the bar itself: `@` is typed INTO it, so there is no control
    // to point at — which is the improvement over the toggle this replaced.
    target: '[data-tour="ask"]',
    title: 'Type @ to name a paper or a thread',
    body:
      'Start any word with @ and suggestions appear as you type: this exploration’s ' +
      'other discussions first, then papers. Arrow onto a paper (or hover it) and Enter ' +
      'opens it on the map; put one inside a question ("what does @… say about X?") and ' +
      'Enter completes the title, then it answers from that paper without disturbing the ' +
      'graph you are looking at. Nothing is picked for you — press Enter with no row ' +
      'chosen and Atlas searches properly for what you typed and lists what it found.',
  },
  {
    target: '[data-tour="search-filters"]',
    title: 'Narrow what can be found',
    body:
      'Restrict a paper search to a publication-year window, a field of study, or ' +
      'both. These are hard limits, not hints — and they apply to the assistant’s own ' +
      'searches too, not just the direct lookup. Citation links on the graph are never ' +
      'filtered: those are edges somebody actually wrote.',
  },
  {
    target: '[data-tour="provider"]',
    title: 'Pick the data source',
    body:
      'The academic database the whole map is built from — Semantic Scholar or OpenAlex, ' +
      'chosen per graph. Each has different strengths (see the note under the graph ' +
      'controls once a map is up); you can rebuild the same paper under the other any time.',
  },
  {
    target: '[data-tour="library-btn"]',
    title: 'Your library',
    body:
      'Bring your own material: textbooks, PDFs, web pages. The assistant can search it, ' +
      'cite passages by page, and pull figures out of your uploaded PDFs into its ' +
      'answers, right alongside the papers on the graph.',
  },
  {
    target: '[data-tour="library-panel"]',
    stage: 'library',
    title: 'Inside the library',
    body:
      'Drop in many PDFs at once (or paste a URL) — each ingests with its own progress ' +
      'row. Everything is chunked and embedded locally: your books never leave this ' +
      'machine. Remove a source any time; the assistant only ever cites what’s here.',
  },
  {
    target: '[data-tour="assistant-panel"]',
    title: 'Every answer is a way in',
    body:
      'Click a paper citation to highlight it on the current graph. A graph icon opens ' +
      'that paper’s graph thread directly. General stays available for searches and broad questions; ' +
      'each graph thread keeps its own conversation. Type @ and pick another discussion to bring it ' +
      'into the one you are in.',
  },
  {
    target: '[data-tour="rail"]',
    title: 'Your explorations live here',
    body:
      'Every exploration saves itself — there is no Save button. Ask a question or open ' +
      'a paper and a row appears here, named after what you were asking about and kept ' +
      'up to date as you work. Threads nest underneath: General for broad questions and ' +
      'one discussion per graph. Use the caret to collapse them, and each ⋮ menu to rename or delete a graph thread. Click a thread to resume it. ✎ starts a new ' +
      'exploration; the one you leave is already saved. Hover a row for ⋮ to rename or ' +
      'delete it, and collapse the whole rail when the map wants the room — click its ' +
      'title row, or drag its right edge; the drag folds it away and pulls it back open.',
  },
  {
    target: '[data-tour="settings-btn"]',
    title: 'Settings',
    body:
      "The app's configuration — data providers, API keys, the citations corpus — " +
      'editable in place. Changes are validated and applied live, no restart.',
  },
]

/**
 * The graph-tools tour, following the eye's path across the screen
 * (re-sequenced with Patrick, v5.22.0): the top-left controls panel walked
 * top-to-bottom through its last row ("Open a paper"), then the
 * bottom-right find control, then the detail panel (a whole-panel overview
 * stop, then its sections), then the teacher — the source scope under the ask
 * bar, then the bar itself, which carries two stops: what the researcher does
 * with a question, and how asking for a lecture reaches the other assistant.
 * The walk follows the eye down the panel and ends where the reader types.
 *
 * It used to open on a lecture grid at the top of the panel. That grid became
 * one button in v7.17.0, was folded behind a caret in v7.10.0, became a
 * `/lecture` command in v7.21.0 — which also deleted the panel's folding
 * sections entirely, so every teacher stop now hangs off the composer — and
 * became plain words in v7.23.0, when the command went.
 * (Find used to open the tour — a leftover from its top-right era; starting on
 * a tiny corner button read as a diagonal jump.)
 * The steps inside the controls panel stage `'controls'` so a
 * collapsed panel expands under the walk; the year/citation stops carry their
 * own target as `presentIf` — an existence check, which the collapsed panel's
 * `hidden` (still-in-DOM) body passes whenever the graph's data earns those
 * sliders at all. `'assistant'` does a narrower job for the teacher: it opens
 * the panel, and that is all it has to do now that nothing in there folds.
 */
export const GRAPH_TOUR: TourStep[] = [
  {
    target: '[data-tour="controls-head"]',
    title: 'The controls panel',
    body:
      'Everything that declutters the map lives under this header. It starts folded to ' +
      'this slim bar so the canvas is yours; the header is a button — click it to open ' +
      'the panel, and again to fold it away. The next stops walk through what’s inside.',
  },
  {
    target: '[data-tour="layout"]',
    stage: 'controls',
    title: 'Two layouts',
    body:
      'Force lets connections cluster the papers; Timeline pins every paper to its ' +
      'publication date, oldest on the left. Switching layouts releases any pinned nodes.',
  },
  {
    target: '[data-tour="relations"]',
    stage: 'controls',
    title: 'Relation filters',
    body:
      'Each chip shows or hides one kind of node, and the chip colors match them. ' +
      'Gold is the seed paper itself — hide it and a lecture covers only the papers around ' +
      'it. Blue references are the papers this one built on; green citations are the ' +
      'papers that built on it — every one of them, from its most-cited classics to work ' +
      'published this year. Which of those you care about is yours to say: the year and ' +
      'citation-count sliders below draw that line however you like.',
  },
  {
    target: '[data-tour="relations"]',
    stage: 'controls',
    // Only while the build is user-sized — Settings ▸ Graph with automatic
    // sizing switched off, which is what grows a slider under each chip. An
    // adaptive graph has none, so the step stays out of the way.
    presentIf: '.rel-cap-slider',
    title: 'How many of each',
    body:
      "Because you've turned off automatic sizing, the graph ships everything it can " +
      'and each chip now heads a count slider. Drag one to keep only that many of that ' +
      'relation, most-cited first — a display trim, so widening it back costs no ' +
      'rebuild. Turn automatic sizing back on in Settings ▸ Graph and the app ' +
      'picks these numbers per paper instead.',
  },
  {
    target: '[data-tour="years"]',
    stage: 'controls',
    presentIf: '[data-tour="years"]',
    title: 'Year window',
    body:
      'Drag the two knobs to keep only papers published inside a span — in Timeline the ' +
      'view zooms into those years.',
  },
  {
    target: '[data-tour="citations"]',
    stage: 'controls',
    presentIf: '[data-tour="citations"]',
    title: 'Citation window',
    body:
      'Bound how cited the visible papers are (a log scale, so the knobs stay useful next ' +
      'to a mega-paper). Trim the long tail, or hide the giants to see what’s underneath.',
  },
  {
    target: '[data-tour="actions"]',
    stage: 'controls',
    title: 'Release · Fit · Refresh · Clear',
    body:
      'Release unpins every node you dragged and re-settles a drifted layout — without ' +
      'moving your zoom. Fit re-centers the whole graph. Refresh rebuilds this ' +
      'paper’s neighborhood fresh from the data provider. Clear drops every highlight ' +
      'at once — your hand-picked papers and the assistant’s glow alike (Esc does the ' +
      'same).',
  },
  {
    target: '[data-tour="selector"]',
    stage: 'controls',
    title: 'Hand-pick what it answers over',
    body:
      'Hold ⌥ Alt and drag a box around papers to add them to the assistant’s scope — ' +
      'sweep several clusters to build one. ⇧ Shift-click toggles a single paper. ' +
      'Lectures and answers then ground in exactly those papers — even ones a filter ' +
      'later hides, which stay drawn with a dotted ring — unless a message names its own. ' +
      'The rings show what a turn is about while it runs and clear when the answer lands; ' +
      'the papers it cited stay lit. Esc clears every highlight at once.',
  },
  {
    target: '[data-tour="hint"]',
    stage: 'controls',
    title: 'Open a paper',
    body:
      'Click any paper to open its detail panel — abstract, figures, code links, tags. ' +
      'Double-click a paper to re-seed the whole map on it and explore from there.',
  },
  {
    target: '[data-tour="find"]',
    title: 'Find a paper on screen',
    body:
      'Click the 🔍 and type part of a title or author. The matching papers light up ' +
      'and everything else dims — all on your screen, nothing is fetched. Pressing ' +
      'Enter (or “select” in the find bar) adds every match to the assistant’s ' +
      'scope. Esc or ✕ clears the find and tucks it away. This only searches what is ' +
      'already drawn — to pull NEW papers in, use the chat bar in the assistant panel.',
  },
  {
    target: '[data-tour="details"]',
    stage: 'details',
    title: 'The paper detail panel',
    body:
      'Everything about the selected paper lives here: how it’s classified, its ' +
      'abstract and TL;DR, links out, community code, and the paper’s own figures. ' +
      'Click any paper on the map to open it — the next stops walk each part.',
  },
  {
    target: '[data-tour="detail-tags"]',
    stage: 'details',
    title: 'Field tags',
    body:
      'How the paper is classified, labeled by who says so — arXiv’s own categories and ' +
      'the data provider’s field-of-study tags, each in its own section.',
  },
  {
    target: '[data-tour="detail-summary"]',
    stage: 'details',
    title: 'Abstract & TL;DR',
    body:
      'Every paper opens on its abstract, and a TL;DR is one click away — Semantic ' +
      'Scholar’s own when it exists. When the tab shows a ✦, clicking it asks Claude ' +
      'to write one. That happens once, and the summary is remembered for good. Math ' +
      'renders properly, subscripts and all.',
  },
  {
    target: '[data-tour="detail-actions"]',
    stage: 'details',
    title: 'Jump off from here',
    body:
      'Open the abstract page or the PDF, Pin the node where you dragged it — or ' +
      '“Explore from here”: rebuild the whole map with this paper as the new seed.',
  },
  {
    target: '[data-tour="detail-code"]',
    stage: 'details',
    title: 'Code & artifacts',
    body:
      'What the community built on this paper, via Hugging Face Papers: the linked ' +
      'GitHub repo (with stars) and the top models, datasets, and Spaces.',
  },
  {
    target: '[data-tour="detail-figures"]',
    stage: 'details',
    title: 'The paper’s own figures',
    body:
      'Real figures pulled from the paper itself, captions included (click one to ' +
      'enlarge). Journal papers get theirs mined straight from the open-access PDF — ' +
      'tables and algorithm boxes included. The teacher can pull these same figures ' +
      'into its answers.',
  },
  {
    target: '[data-tour="source-scope"]',
    stage: 'assistant',
    presentIf: '[data-tour="source-scope"]',
    title: 'Which sources it may search',
    body:
      'Scope the researcher’s library reach: all of your sources, a subset, or none at ' +
      'all. Checked means searchable — answers cite whatever passages they use by page. ' +
      'Untick everything and the assistant leaves your library alone, which works with ' +
      'a single uploaded source too.',
  },
  {
    target: '[data-tour="ask"]',
    stage: 'assistant',
    presentIf: '[data-tour="assistant-btn"]',
    title: 'One bar, two assistants',
    body:
      'Ask anything about what’s on screen. The agent grounds in the papers you’ve ' +
      'selected — or in every visible paper when you haven’t picked any. It reads them ' +
      'in full, hops the graph, searches the literature and your uploaded library, then ' +
      'answers with numbered citations (click one to highlight its paper on the graph). New ' +
      'papers it finds join the map with dashed rings. ' +
      'Press Enter to send; ⇧ Shift+Enter starts a new line for longer questions.',
  },
  {
    target: '[data-tour="ask"]',
    stage: 'assistant',
    presentIf: '[data-tour="assistant-btn"]',
    title: 'Ask to be taught, not answered',
    body:
      'Ask for a lecture in the same bar — “lecture me on these”, “what’s the story ' +
      'here?” — and the other assistant narrates the papers you have on screen, so you ' +
      'decide what it is about. Filter to the references and you get the story of how ' +
      'the field arrived here; keep only recent work and you get the current frontier; ' +
      'alt-drag a cluster and it narrates just those. Scope it to a single paper — any ' +
      'paper — and it teaches that one, chapter by chapter. Or say which papers in the ' +
      'message itself: “lecture me on the references”, “on the seed”, “on the Bekenstein ' +
      'paper and Hawking 1975”, “the whole graph”, “the papers between 2016 and 2017” — those become the ' +
      'selection, drawn even if a filter hides them, and are narrated; questions scope ' +
      'the same way, and each reply says what it was scoped to. When a ' +
      'lecture finishes the whole of it stays lit. Say “history” and it walks them oldest ' +
      'to newest; otherwise it groups them into their key themes. Papers light up on the ' +
      'map as each part of the story arrives, and the beats read as the reply, in the ' +
      'conversation with everything else. Every turn it guessed on says which assistant ' +
      'answered and offers the other in a click, so a wrong guess costs nothing.',
  },
]
