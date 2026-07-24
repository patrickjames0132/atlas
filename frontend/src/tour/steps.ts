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
 * panel needs a selected paper, the lecture grid needs the assistant open),
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

/** The startup tour: the search surface, before any graph is loaded. */
export const HOME_TOUR: TourStep[] = [
  {
    target: '[data-tour="search"]',
    title: 'Start with a paper',
    body:
      'Search any paper by title — or paste an arXiv id or URL to jump straight to it. ' +
      'Atlas maps the paper’s neighborhood: what it built on, who built on it, and ' +
      'what’s happening there right now.',
  },
  {
    target: '[data-tour="search-options"]',
    title: 'Tune the search',
    body:
      'Optional settings for the title search. Narrow it with a publication-year window ' +
      'or a field-of-study picker. The search only matches words, so “DQN” would miss ' +
      'papers that never spell it out — by default an AI model adds the full terms ' +
      'first, and you can turn that off. A pasted id or URL ignores all of this and ' +
      'loads its paper directly.',
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
      'Bring your own material: textbooks, PDFs, web pages. The AI teacher can search it, ' +
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
    target: '[data-tour="assistant-btn"]',
    title: 'The AI assistant',
    body:
      'One panel, two levels: with no graph open it chats over your uploaded library; ' +
      'once a graph is up it lectures over the map and researches your questions with ' +
      'real tools — and it keeps drawing on your library too, for whichever sources you ' +
      'leave selected in its 📚 scope.',
  },
  {
    target: '[data-tour="assistant-panel"]',
    stage: 'assistant',
    presentIf: '[data-tour="assistant-btn"]',
    title: 'Chat with your books',
    body:
      'Ask a question and the assistant retrieves the most relevant passages from your ' +
      'library and answers grounded in them, citing by page — "(Deep Learning, p.243)". ' +
      'Scope it to specific sources with the 📚 picker above the ask bar.',
  },
  {
    target: '[data-tour="sessions-btn"]',
    title: 'Sessions',
    body:
      'Save the whole workspace — the graph as you built it, every paper the teacher ' +
      'discovered, and the conversation — and come back to it later.',
  },
  {
    target: '[data-tour="sessions-panel"]',
    stage: 'sessions',
    title: 'Saved sessions',
    body:
      'Save as new or update one in place; reopening rebuilds the exact graph from the ' +
      'save itself — zero API calls, discovered papers included — and the transcript ' +
      'comes back with it.',
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
 * stop, then its sections), then the teacher — where the two scope pickers
 * (lectures, then library sources) come before the lecture grid. (Find
 * used to open the tour — a leftover from its top-right era; starting on
 * a tiny corner button read as a diagonal jump.)
 * The steps inside the controls panel stage `'controls'` so a
 * collapsed panel expands under the walk; the year/citation stops carry their
 * own target as `presentIf` — an existence check, which the collapsed panel's
 * `hidden` (still-in-DOM) body passes whenever the graph's data earns those
 * sliders at all.
 */
export const GRAPH_TOUR: TourStep[] = [
  {
    target: '[data-tour="controls-head"]',
    title: 'The controls panel',
    body:
      'Everything that declutters the map lives under this header. The header is also ' +
      'a button. Click it to collapse the whole panel to a slim bar when you want the ' +
      'canvas space back, and click it again to reopen. The next stops walk through ' +
      'what’s inside.',
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
      'Each chip shows or hides one kind of neighbor, and the chip colors match the ' +
      'nodes. Blue references are the papers this one built on. Both greens are ' +
      'citations — papers that built on it: deep-green Field Landmarks are its ' +
      'most-cited citers of all time, pale-green Latest Publications the newest ones ' +
      'at the frontier. Same relationship, two eras.',
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
      'at once — your hand-picked papers and the teacher’s glow alike (Esc does the ' +
      'same).',
  },
  {
    target: '[data-tour="selector"]',
    stage: 'controls',
    title: 'Hand-pick the teacher’s scope',
    body:
      'Hold ⌥ Alt and drag a box around papers to add them to the AI teacher’s scope — ' +
      'sweep several clusters to build one. ⇧ Shift-click toggles a single paper. ' +
      'Lectures and answers then ground in exactly those papers — and Esc clears ' +
      'every highlight at once, the pick and the teacher’s glow alike.',
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
      'Enter (or “select” in the search bar) adds every match to the AI teacher’s ' +
      'scope. Esc or ✕ clears the find and tucks it away. To pull new papers in, use ' +
      'the search box up top.',
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
    target: '[data-tour="lecture-scope"]',
    stage: 'assistant',
    presentIf: '[data-tour="lecture-scope"]',
    title: 'Which lectures feed the answers',
    body:
      'The lectures you’ve played so far — the researcher builds on what they already ' +
      'said instead of re-deriving it. Untick any you’d rather it ignore; a note above ' +
      'the ask bar shows how many are in play.',
  },
  {
    target: '[data-tour="source-scope"]',
    stage: 'assistant',
    presentIf: '[data-tour="source-scope"]',
    title: 'Which sources it may search',
    body:
      'Scope the researcher’s library reach (shown once you have two or more sources): ' +
      'all of them, a subset, or none at all. Checked means searchable — answers cite ' +
      'whatever passages they use by page.',
  },
  {
    target: '[data-tour="lectures"]',
    stage: 'assistant',
    presentIf: '[data-tour="assistant-btn"]',
    title: 'Four lectures',
    body:
      'Four stories, each told over one slice of the graph — and each button wears its ' +
      'slice’s color. Blue walks the references: how the field arrived at this paper. ' +
      'Green covers the landmark papers that built on it. Light green surveys the ' +
      'current frontier. Gold teaches the seed paper itself, chapter by chapter. Papers ' +
      'light up on the map as their part of the story arrives — and once a lecture has ' +
      'played, a 🎓 scope picker appears in the panel header so the researcher can build ' +
      'on it in Q&A.',
  },
  {
    target: '[data-tour="ask"]',
    stage: 'assistant',
    presentIf: '[data-tour="assistant-btn"]',
    title: 'Ask the researcher',
    body:
      'Ask anything about what’s on screen. Like the lectures, the agent grounds in ' +
      'the papers you’ve selected — or in every visible paper when you haven’t picked ' +
      'any. It reads them in full, hops the graph, searches the literature and your ' +
      'uploaded library, then answers with numbered citations (click one to light up ' +
      'the paper behind it). New papers it finds join the map with dashed rings. ' +
      'Press Enter to send; ⇧ Shift+Enter starts a new line for longer questions.',
  },
]
