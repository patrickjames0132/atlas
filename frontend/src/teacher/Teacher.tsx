/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The unified assistant — a slim shell around one conversation, rendered in
 * two shapes and at two capability levels. The shapes:
 *   • `landing` — no graph yet, so the chat owns the whole body as a centred
 *     column. This is the app's front door, and needs neither a graph nor an
 *     uploaded library to be useful.
 *   • docked — a graph is open, so it collapses to a resizable side panel
 *     beside the map.
 * The capability, independently:
 *   • No graph → the researcher, seedless: the literature plus whatever
 *     sources the reader has uploaded.
 *   • A graph is open → the streaming lecture + agentic Q&A over it.
 *
 * **The two shapes are one component instance, deliberately.** The shell keeps
 * it at a single position in the tree and only swaps the `landing` flag, so
 * entering graph mode collapses the chat into the panel without remounting —
 * the conversation, its scroll position and its run state all survive. That
 * is the whole point of clicking a cited paper: the answer you were reading is
 * still there when its graph arrives. (`epoch`, which the parent keys on, no
 * longer bumps on a graph load for the same reason — only Home and a session
 * restore remount.)
 *
 * **Docked, the panel is a stack of folding sections** (v7.10.0): *Lectures*
 * — the four mode buttons and whichever lecture is shown — and *Chat*, the
 * conversation, whose caret row also carries every control that binds the ask:
 * the 🎓/📚 scope pickers and the 🔍/▽ search controls, because those scope
 * the researcher answering there rather than the lecturer above.
 * Before this the two shared one scroll and took turns: playing a lecture hid
 * the chat, asking a question hid the lecture. Sections let a reader keep a
 * lecture open and ask about it. With no graph there is nothing to divide, so
 * the conversation simply is the panel.
 *
 * **The ask bar itself holds nothing but the question** (v7.11.0). Those four
 * controls all used to sit inside the pill, which made the one thing you came
 * here to use — a box to type in — read as a toolbar with a text field wedged
 * in it. Without a graph they moved out to a chip row directly beneath the
 * bar; with one, up to the Chat row above it. Either way they stay adjacent to
 * the ask they modify, and the bar goes back to looking like a bar.
 *
 * The conversation itself lives in the store (transcript slice) and the
 * stream orchestration in useConversation; this component owns only what it
 * alone renders — the input box, the section folds, the scope picker's data,
 * the lightbox. A restored session's transcript arrives via the store, no
 * seeding props needed.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, FormEvent, KeyboardEvent } from 'react'
import {
  DEFAULT_SEARCH_OPTIONS,
  LECTURE_TITLES,
  type AnswerFigure,
  type LectureMode,
  type SearchOptions,
} from '../api'
import { useAppDispatch, useAppSelector } from '../store'
import { selectSatelliteCount } from '../store/workspace'
import { loadLibrary, selectLibrary } from '../store/library'
import { selectVisibleBeats, selectVisibleSourceRefs } from '../store/transcript'
import { REL_COLOR } from '../graph/theme'
import HopDots from './HopDots'
import ScopePicker from './ScopePicker'
import SearchControls from '../search/SearchControls'
import { useDirectSearch } from '../search/useDirectSearch'
import { ID_RE } from '../graph/model'
import Lightbox from '../figures/Lightbox'
import BeatList from './transcript/BeatList'
import ChatMessage from './transcript/ChatMessage'
import { useConversation } from './useConversation'
import { useResizablePanel } from '../ui/useResizablePanel'
import './teacher.css'

// Each lecture narrates one graph relation, so its button is tinted that
// relation's node colour (`rel` → REL_COLOR) and carries a small `tag` in the
// top-right corner naming the relation — the same colour as the graph's filter
// chips and legend dots, so the button visibly ties to the nodes it lights up.
const MODES: { key: LectureMode; label: string; rel: string; tag: string }[] = [
  { key: 'history', label: LECTURE_TITLES.history, rel: 'reference', tag: 'References' },
  { key: 'intuition', label: LECTURE_TITLES.intuition, rel: 'seed', tag: 'This paper' },
  { key: 'evolution', label: LECTURE_TITLES.evolution, rel: 'citation', tag: 'Landmarks' },
  { key: 'frontier', label: LECTURE_TITLES.frontier, rel: 'latest', tag: 'Latest' },
]

/**
 * The bin the two Clear controls share — the composer's (which wipes the
 * conversation) and the Lectures row's (which drops the shown lecture).
 *
 * @returns The inline glyph.
 */
function ClearGlyph() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M3.2 4.6h9.6M6.5 4.6V3.3a.8.8 0 0 1 .8-.8h1.4a.8.8 0 0 1 .8.8v1.3M4.8 4.6l.45 7.9a1.1 1.1 0 0 0 1.1 1h3.3a1.1 1.1 0 0 0 1.1-1l.45-7.9"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * Whether the reader has asked the OS for less motion.
 *
 * The CSS entrances answer this with a `prefers-reduced-motion` block; the
 * composer's FLIP is scripted, so it has to ask directly. Read at call time,
 * never at module scope — this module is imported by tests running in the
 * node environment, where there is no `window` at all.
 *
 * @returns True when motion should be skipped.
 */
function prefersStill(): boolean {
  return (
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * Render the assistant panel: lecture buttons, transcript, and the ask form.
 *
 * @returns The docked, resizable assistant panel.
 */
export default function Teacher({
  collapsed = false,
  landing = false,
  stagedOpen = false,
  onClose,
}: {
  /** Hidden (but kept mounted, so the conversation survives) when collapsed. */
  collapsed?: boolean
  /**
   * This is the landing surface, not a docked side panel: no graph is open, so
   * the conversation gets the whole body as a centred column. Deliberately the
   * *same component instance* as the docked panel — the shell keeps it at one
   * position in the tree and only swaps this flag, so entering graph mode
   * collapses the chat into the side panel without remounting it, and the
   * answer you were reading keeps its scroll position.
   */
  landing?: boolean
  /**
   * The guided tour has staged the assistant open, so expand the lecture
   * section for the walk — its "Four lectures" step targets the grid, which
   * is folded away by default. Mirrors GraphControls' prop of the same name,
   * and like that one it only ever *opens*: a reader who folds the lectures
   * back mid-tour keeps them folded.
   */
  stagedOpen?: boolean
  /** Collapse the panel (the header ✕). */
  onClose?: () => void
}) {
  const chat = useAppSelector((state) => state.transcript.chat)
  const beats = useAppSelector(selectVisibleBeats)
  const lectureSourceRefs = useAppSelector(selectVisibleSourceRefs)
  const lectures = useAppSelector((state) => state.transcript.lectures)
  const activeMode = useAppSelector((state) => state.transcript.activeMode)
  // How many nodes the user has hand-picked on the graph (alt-drag / shift-click)
  // to scope the teacher; 0 means it grounds in every visible paper.
  const pickedCount = useAppSelector((state) => state.workspace.selectedNodeIds.length)
  // Papers on the graph that hang off another paper rather than the seed —
  // the ones no lecture will narrate (see the lecture intro).
  const satelliteCount = useAppSelector(selectSatelliteCount)
  const {
    hasGraph,
    loadingModes,
    asking,
    error,
    activeBeat,
    activeChat,
    onBeatClick,
    onChatClick,
    onRefClick,
    onGraphIds,
    onPaperSeed,
    provider,
    toggleLecture,
    ask,
    stopAsk,
    clearLecture,
    clearChat,
  } = useConversation()

  // Each section owns its own Clear now that both are on screen at once: the
  // lecture's sits on the Lectures row, and this one — in the composer, which
  // belongs to Q&A — wipes the conversation.
  // The shown lecture's metadata (name + relation colour), for the transcript's
  // "Now playing" header. null when no lecture is shown (a Q&A chat, or idle).
  const activeModeMeta = MODES.find((mode) => mode.key === activeMode) ?? null

  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  // The lecture buttons, folded away behind their caret. INITIAL VALUE ONLY —
  // once opened they stay open for the session, because the four modes are a
  // menu you come back to. Folded is the default because the grid sat
  // permanently expanded directly above the ask box, spending the panel's
  // prime vertical space on four buttons most turns never press; a first-time
  // reader still meets them through the tour, which stages this open.
  const [lecturesOpen, setLecturesOpen] = useState(false)
  // The conversation, on the other hand, starts open: it is what the composer
  // below writes into, and a reader who folds it away has said so deliberately.
  const [chatOpen, setChatOpen] = useState(true)
  // The uploaded library, powering the source-scope picker (shown whenever
  // there is anything to scope — see the render site for why one source
  // counts). Read LIVE from the library slice — the Sources drawer reloads
  // the slice on every upload/delete, so the picker appears the moment a
  // source lands (it used to sit on a stale mount-time fetch until a page
  // reload).
  const dispatch = useAppDispatch()
  const { sources: libraryItems, loaded: libraryLoaded } = useAppSelector(selectLibrary)
  // Sources the assistant may NOT search — tracked by EXCLUSION (mirroring
  // excludedLectures below) so a source uploaded after the user last touched
  // the picker is searchable by default. Checked = current sources minus
  // these; a deleted source's lingering id here is inert.
  const [excludedSources, setExcludedSources] = useState<string[]>([])
  // Lectures the researcher may NOT use as context, tracked by EXCLUSION so a
  // lecture played after the user last touched the picker is fed by default.
  const [excludedLectures, setExcludedLectures] = useState<LectureMode[]>([])
  // Which scope picker's popover is open — one shared slot, so opening either
  // picker closes the other (their popovers overlap when both are open).
  const [openScope, setOpenScope] = useState<'lectures' | 'sources' | 'filters' | null>(null)
  // Direct search armed: the next send goes to the paper scout and comes
  // back as a list to pick from, instead of to the researcher for an answer.
  const [direct, setDirect] = useState(false)
  // The bar's filters. They bind BOTH modes (see api/search.ts), which is
  // why they live out here beside the input rather than inside `direct`.
  const [searchOptions, setSearchOptions] = useState<SearchOptions>(DEFAULT_SEARCH_OPTIONS)
  // The answer figure opened full-screen (null = closed).
  const [lightbox, setLightbox] = useState<AnswerFigure | null>(null)
  // Direct search's own failure slot. Separate from the conversation's
  // `error` because only a transport failure lands here — the scout
  // degrades internally, so a rate-limited provider arrives as a normal
  // result whose summary says so.
  const [searchError, setSearchError] = useState<string | null>(null)
  const { width, onHandlePointerDown, dragging } = useResizablePanel('atlas.teacherWidth', 340)
  // Direct search shares the bar's busy state with the researcher: one bar,
  // one spinner, and neither mode can be fired while the other is running.
  const { searching, runSearch } = useDirectSearch(provider, searchOptions, setSearchError)

  // First reader fetches; the loaded flag keeps the drawer (and the remounts
  // that Home and a session restore still cause) from re-fetching a library
  // the store already holds.
  useEffect(() => {
    if (!libraryLoaded) dispatch(loadLibrary())
  }, [libraryLoaded, dispatch])

  // The tour walks to the lecture grid and to the Q&A row's scope pickers, so
  // unfold both first — a spotlight on a hidden element has nothing to point at.
  useEffect(() => {
    if (stagedOpen) {
      setLecturesOpen(true)
      setChatOpen(true)
    }
  }, [stagedOpen])

  // Checked = the assistant may search that source (everything not excluded).
  const scopeIds = libraryItems
    .filter((source) => !excludedSources.includes(source.id))
    .map((source) => source.id)
  // "No scope" (search the whole library) only when every source is checked;
  // any other state is sent as an explicit id list (empty = search nothing).
  const scopeAll = libraryItems.length === 0 || scopeIds.length === libraryItems.length
  const scopeArg = scopeAll ? undefined : scopeIds

  // The played lectures, and which of them the researcher may use as context
  // (the checked ones — all played minus the user's exclusions).
  const playedModes = MODES.map((mode) => mode.key).filter(
    (key) => (lectures[key]?.length ?? 0) > 0,
  )
  const lectureScope = playedModes.filter((mode) => !excludedLectures.includes(mode))
  const lectureItems = playedModes.map((mode) => ({ id: mode, title: LECTURE_TITLES[mode] }))

  // One bar, three destinations — and which one runs is decided HERE, before
  // any model is involved, rather than by asking an agent to classify the
  // input. A pasted id is exact, so it needs nothing but a regex; direct
  // search is deterministic apart from the queries the scout writes; only the
  // third is open-ended.
  const submitQuestion = () => {
    const question = input.trim()
    if (!question || asking || searching) return
    setInput('')
    // Whatever this turns into lands in the conversation, so make sure the
    // reader can see it — asking into a folded section reads as nothing
    // happening at all.
    setChatOpen(true)
    // A pasted arXiv id/URL is a statement of intent, not a question: land on
    // that exact paper. Deliberately ahead of the direct-search toggle — you
    // pasted the paper, so there is nothing left to search for, whichever
    // mode happens to be armed.
    if (ID_RE.test(question)) {
      onPaperSeed(question)
      return
    }
    if (direct) {
      void runSearch(question)
      return
    }
    ask(question, scopeArg, lectureScope, searchOptions)
  }

  const onAsk = (event: FormEvent) => {
    event.preventDefault()
    submitQuestion()
  }

  // The ask box is a textarea so long questions wrap and stay readable. Keep
  // the chat convention: Enter sends, Shift+Enter drops a newline (letting a
  // question run multiple lines without hitting the Ask button).
  const onInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submitQuestion()
    }
  }

  // Grow the textarea to fit its content (up to the CSS max-height, past which
  // it scrolls): reset to auto so it can shrink back, then match scrollHeight.
  // Runs on every input change, including the reset to '' after a submit.
  // A collapsed panel is display:none, so a first mount there measures
  // scrollHeight 0 — skip that, leaving height:auto (the CSS min-height floors
  // it to one line) rather than pinning it to a clipped 0px until the next keystroke.
  useEffect(() => {
    const field = inputRef.current
    if (!field) return
    field.style.height = 'auto'
    if (field.scrollHeight > 0) field.style.height = `${field.scrollHeight}px`
  }, [input])

  // Follow the bottom while an answer builds. Trace chips, tokens and beats all
  // arrive at the end of the transcript, and without this they simply grow past
  // the fold — the reader watches the agent work right up until the moment the
  // work scrolls out of sight.
  //
  // Conditional on purpose: it follows only while the reader is already AT the
  // bottom. Scroll up mid-answer to re-read something and the transcript stops
  // chasing, because yanking someone back down is worse than the problem this
  // solves; scroll back down and it resumes. The threshold is generous — a few
  // pixels of rounding, or a half-line of overshoot, still counts as "at the
  // bottom", and `.chat`'s entrance transform means the last element is briefly
  // 16px lower than its resting place while it animates in.
  const scrollRef = useRef<HTMLDivElement>(null)
  const following = useRef(true)
  const onTranscriptScroll = () => {
    const box = scrollRef.current
    if (box) following.current = box.scrollHeight - box.scrollTop - box.clientHeight < 40
  }
  useEffect(() => {
    const box = scrollRef.current
    if (!box || !following.current) return
    // Instant, never smooth: a smooth scroll can't keep up with SSE frames, and
    // several in flight at once fight each other into a visible judder.
    box.scrollTop = box.scrollHeight
  }, [chat, beats])

  // The composer's drop, on the first question of a landing session. Empty, it
  // sits optically centred with the greeting; the moment a conversation starts
  // it belongs at the bottom with the transcript filling in above. That move is
  // a flex-layout change, which CSS cannot transition — so this is a FLIP:
  // remember where the bar *was* on the last commit, and once the browser has
  // put it in its new place, animate it from the old position to the new one.
  // Nothing in the layout is faked; only a transform is played over the top.
  //
  // Keyed on `empty` alone, and deliberately not on every render: reading
  // getBoundingClientRect forces layout, and this component re-renders on every
  // streamed token.
  const askRef = useRef<HTMLDivElement>(null)
  const askTop = useRef<number | null>(null)
  const wasEmpty = useRef(false)
  const empty = landing && chat.length === 0
  useLayoutEffect(() => {
    const bar = askRef.current
    if (!bar) return
    const from = askTop.current
    if (wasEmpty.current && !empty && from !== null && !prefersStill()) {
      const travelled = from - bar.getBoundingClientRect().top
      // `animate` is optional-called: jsdom has no Web Animations API, so a
      // component test would otherwise die on a purely decorative flourish.
      if (travelled) {
        bar.animate?.(
          [{ transform: `translateY(${travelled}px)` }, { transform: 'translateY(0)' }],
          // Paced with the CSS entrances (`rise-in`, teacher.css) and eased
          // the same way — this travels much further than any of them, so it
          // gets the longer end of the range. Retune the two together.
          { duration: 560, easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)' },
        )
      }
    }
    wasEmpty.current = empty
    askTop.current = bar.getBoundingClientRect().top
  }, [empty])

  // What the ask bar invites, which is not always the same offer. The old copy
  // promised books and PDFs whenever there was no graph — fine back when a
  // library was the price of admission, and a lie now that the assistant is
  // the landing surface for everyone. Only name the library when there is one.
  const askPlaceholder = hasGraph
    ? 'Ask about the papers on screen…'
    : libraryItems.length > 0
      ? 'Ask your books, PDFs, or the literature…'
      : 'Ask a research question…'

  // The one-line "Answers also draw on …" note above the ask bar: lectures and
  // sources share it (space is tight), each part naming its picker's icon.
  // Only what's actually in play appears — no lectures played and no sources
  // scoped means no note.
  //
  // Graph mode only, both halves. There the two pickers are bare icons on the
  // Chat row and this line is the only place their state is spelled out; with
  // no graph the tool row under the bar wears its own labels ("2 sources"),
  // so the note would be saying the same thing twice a centimetre apart.
  const askContextParts: string[] = []
  if (hasGraph) {
    if (lectureScope.length > 0) {
      askContextParts.push(
        `${lectureScope.length} played lecture${lectureScope.length > 1 ? 's' : ''} (🎓)`,
      )
    }
    if (scopeIds.length > 0) {
      askContextParts.push(`${scopeIds.length} source${scopeIds.length > 1 ? 's' : ''} (📚)`)
    }
  }

  // Which sources the researcher may search. ONE picker, rendered in one of
  // two places depending on the shape the panel is in — but never *inside* the
  // ask bar any more (v7.11.0). It sat there, with the two search controls
  // beside it, until the pill was three controls and a textarea and read as
  // clutter: the box you type in should look like a box you type in. So:
  //   • no graph — down in the tool row directly under the bar, still plainly
  //     part of the question you are about to ask, and with the room to wear
  //     its label;
  //   • docked — up on the Chat section's row beside the 🎓 lecture scope,
  //     because beside a graph the panel is ~340px and nothing fits in the
  //     pill. That row already hosts exactly this kind of control.
  // At ONE source too, not two. The gate used to be `> 1` on the reading that
  // a lone source leaves no choice to make — but "use it / don't" is a choice,
  // and it's the one a reader with a single uploaded book most wants: without
  // the picker there was no way to ask a question *without* their textbook in
  // play. The empty scope (`scopeArg = []`) was already plumbed end to end.
  const sourcePicker = libraryItems.length > 0 && (
    <ScopePicker
      items={libraryItems}
      checkedIds={scopeIds}
      dataTour="source-scope"
      open={openScope === 'sources'}
      onOpenChange={(nowOpen) => setOpenScope(nowOpen ? 'sources' : null)}
      onToggle={(id) =>
        setExcludedSources((prev) =>
          prev.includes(id) ? prev.filter((other) => other !== id) : [...prev, id],
        )
      }
      onSelectAll={() => setExcludedSources([])}
      onDeselectAll={() => setExcludedSources(libraryItems.map((source) => source.id))}
      labels={{
        icon: '📚',
        unit: 'source',
        heading: 'Search in',
        allHint: 'All sources are searched.',
        someHint: 'Only the checked sources are searched.',
        noneHint: "No sources selected — the assistant won't search your library.",
        buttonTitle: 'Choose which of your sources the assistant may search',
      }}
    />
  )

  // The two search controls (arm direct search · open the filters), and they
  // travel with the source picker above for the same reason and to the same
  // two places — the tool row under the bar without a graph, the Chat row with
  // one. Their filter popover anchors to whichever container it lands in, so
  // it still spans the panel rather than the button that opened it.
  const searchControls = (
    <SearchControls
      direct={direct}
      onDirectChange={setDirect}
      options={searchOptions}
      onOptions={setSearchOptions}
      provider={provider}
      open={openScope === 'filters'}
      onOpenChange={(nowOpen) => setOpenScope(nowOpen ? 'filters' : null)}
    />
  )

  // The conversation's turns, rendered identically wherever they land — in
  // the Q&A section beside a graph, or as the whole panel without one.
  const chatTurns = chat.map((message, index) => {
    // Clicking the bubble re-lights the answer's whole grounding set — so it's
    // only a control while at least one of those papers is actually on the
    // graph. Since the conversation now outlives the graph it was written
    // against, an older answer can cite nothing that's still loaded, and a
    // clickable bubble that highlights nothing is the same dead pointer its
    // `[n]` chips grey out for. Partial overlap still counts: lighting the
    // papers that *are* here is useful.
    const clickable =
      message.role === 'assistant' &&
      !!message.cited &&
      message.cited.some((nodeId) => onGraphIds.has(nodeId))
    return (
      <ChatMessage
        key={`c${index}`}
        message={message}
        active={activeChat === index}
        streaming={asking || searching}
        onActivate={clickable ? () => onChatClick(index, message.cited!) : undefined}
        onRefClick={onRefClick}
        onGraphIds={onGraphIds}
        onPaperSeed={onPaperSeed}
        provider={provider}
        onEnlarge={setLightbox}
      />
    )
  })

  return (
    <section
      className={`teacher${landing ? ' landing' : ''}${landing && chat.length === 0 ? ' empty' : ''}${collapsed ? ' collapsed' : ''}`}
      data-tour="assistant-panel"
      style={landing ? undefined : { width }}
    >
      {/* Nothing to resize against on the landing surface — it owns the body. */}
      {!landing && (
        <div
          className={`panel-resize-handle${dragging ? ' dragging' : ''}`}
          onPointerDown={onHandlePointerDown}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panel"
        />
      )}
      <div className="teacher-head">
        {/* The landing surface has no panel title and nothing to close — the
            row would be an empty strip of chrome. */}
        {!landing && (
          <div className="teacher-head-top">
            <span className="teacher-title">
              {hasGraph ? 'AI Teacher & Discovery' : 'Ask the assistant'}
            </span>
            <div className="teacher-head-right">
              {onClose && (
                <button
                  className="link-btn"
                  onClick={onClose}
                  aria-label="Close the assistant panel"
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* One scroller, holding the panel's sections. Each section folds behind
          its own caret, and both can be open at once — which is the whole
          point of the split: the lecture you are reading and the question you
          just asked no longer take turns owning this space. The follow-the-
          bottom effect above watches this box, so a streaming answer still
          keeps itself in view. */}
      <div className="teacher-scroll" ref={scrollRef} onScroll={onTranscriptScroll}>
        {hasGraph ? (
          <>
            <section className="panel-section">
              <div className="section-head">
                <button
                  type="button"
                  className={`section-toggle${lecturesOpen ? ' open' : ''}`}
                  onClick={() => setLecturesOpen((open) => !open)}
                  aria-expanded={lecturesOpen}
                  title={
                    lecturesOpen
                      ? 'Fold the lectures away'
                      : 'Play a lecture — four narrated tours of the papers on the graph'
                  }
                >
                  <span className="section-caret" aria-hidden="true">
                    ▸
                  </span>
                  <span className="section-name">Lectures</span>
                  {/* Folded, this row is the only place a generating lecture
                      can report itself — its button's dots are out of sight.
                      The app's shared spinner rather than those dots: the dots
                      are a *voice* ("an agent is composing" — a lecture button,
                      the send control, a bubble awaiting its first token), and
                      a section header is a status line. Same reasoning as the
                      trace chips. */}
                  {!lecturesOpen && loadingModes.length > 0 && (
                    <span
                      className="spin section-spin"
                      role="status"
                      aria-label="Loading lecture"
                    />
                  )}
                </button>
                {activeModeMeta && (
                  <button
                    type="button"
                    className="section-clear"
                    onClick={clearLecture}
                    title={`Clear ${activeModeMeta.label}`}
                    aria-label="Clear lecture"
                  >
                    <ClearGlyph />
                  </button>
                )}
              </div>
              <div className="section-body" hidden={!lecturesOpen}>
                <p className="lecture-intro">
                  Play a lecture to summarize different node types. Each lecture is grounded in the
                  papers currently shown on the graph — filter it, or alt-drag on the canvas to
                  hand-pick a cluster, to narrow what it covers.
                  {/* Said here rather than left for the reader to notice: once you
                      expand a paper, its own neighbours are on the graph but are
                      not this seed's references or citers, so no lecture covers
                      them. Without this line their absence looks like the lecture
                      quietly skipping papers. */}
                  {satelliteCount > 0 && (
                    <>
                      {' '}
                      <strong>
                        {satelliteCount} paper{satelliteCount > 1 ? 's' : ''} you expanded
                      </strong>{' '}
                      {satelliteCount > 1 ? 'sit' : 'sits'} outside this paper’s own neighbourhood —
                      a lecture won’t cover {satelliteCount > 1 ? 'them' : 'it'}. Re-seed on one to
                      hear its story.
                    </>
                  )}
                </p>
                <div className="lecture-grid" data-tour="lectures">
                  {MODES.map((mode) => {
                    const active = activeMode === mode.key
                    const loading = loadingModes.includes(mode.key)
                    // The "click to show" dot marks a played-but-hidden lecture;
                    // a loading one shows its hopping dots instead.
                    const cached = !loading && (lectures[mode.key]?.length ?? 0) > 0
                    // The button shows only the short node-type word; the full
                    // lecture name rides in the tooltip, the aria-label, and the
                    // "Now playing" header below.
                    const stateHint = loading
                      ? active
                        ? 'click to hide (still loading)'
                        : 'loading — click to show'
                      : active
                        ? 'click to hide'
                        : cached
                          ? 'click to show'
                          : 'click to play'
                    return (
                      <button
                        key={mode.key}
                        className={`teach-btn${active ? ' active' : ''}${
                          cached && !active ? ' cached' : ''
                        }`}
                        style={{ '--c': REL_COLOR[mode.rel] } as CSSProperties}
                        // Lectures load in parallel — every button stays live so
                        // you can show/hide or start another while one generates.
                        onClick={() => toggleLecture(mode.key)}
                        aria-pressed={active}
                        aria-label={mode.label}
                        title={`${mode.label} — ${stateHint}`}
                      >
                        {loading ? <HopDots label="Loading lecture" /> : mode.tag}
                      </button>
                    )
                  })}
                </div>
                {/* The shown lecture reads inside its own section now, rather
                    than taking over the panel's one scroll. */}
                {activeModeMeta && (
                  <>
                    <div
                      className="lecture-now"
                      style={{ '--c': REL_COLOR[activeModeMeta.rel] } as CSSProperties}
                    >
                      <span className="lecture-now-eyebrow">Now playing</span>
                      <span className="lecture-now-title">{activeModeMeta.label}</span>
                    </div>
                    <BeatList
                      beats={beats}
                      sourceRefs={lectureSourceRefs}
                      activeBeat={activeBeat}
                      onBeatClick={onBeatClick}
                      onRefClick={onRefClick}
                      onGraphIds={onGraphIds}
                      onEnlarge={setLightbox}
                    />
                    {beats.length === 0 && loadingModes.includes(activeModeMeta.key) && (
                      <div className="teacher-hint">Preparing the lecture…</div>
                    )}
                  </>
                )}
              </div>
            </section>

            <section className="panel-section">
              <div className="section-head">
                <button
                  type="button"
                  className={`section-toggle${chatOpen ? ' open' : ''}`}
                  onClick={() => setChatOpen((open) => !open)}
                  aria-expanded={chatOpen}
                  title={chatOpen ? 'Fold the conversation away' : 'Show the conversation'}
                >
                  <span className="section-caret" aria-hidden="true">
                    ▸
                  </span>
                  <span className="section-name">Chat</span>
                  {/* Unlike the lecture row's, this one shows whether the
                      section is folded or not: the header is pinned, so while
                      you scroll back through a long history it is the only
                      thing still on screen that can tell you the agent is
                      still writing. */}
                  {(asking || searching) && (
                    <span className="spin section-spin" role="status" aria-label="Answering" />
                  )}
                </button>
                {/* Every control that binds the ask lives HERE, not in the
                    panel header and no longer in the bar itself: the two
                    scopes (🎓 lectures, 📚 sources) and the two search
                    controls (🔍 direct search, ▽ filters). All four bind the
                    researcher answering below, not the lecturer above, and
                    docked there is no room for any of them in the pill. */}
                <div className="section-head-right">
                  {playedModes.length > 0 && (
                    <ScopePicker
                      items={lectureItems}
                      checkedIds={lectureScope}
                      dataTour="lecture-scope"
                      open={openScope === 'lectures'}
                      onOpenChange={(nowOpen) => setOpenScope(nowOpen ? 'lectures' : null)}
                      onToggle={(id) =>
                        setExcludedLectures((prev) =>
                          prev.includes(id as LectureMode)
                            ? prev.filter((mode) => mode !== id)
                            : [...prev, id as LectureMode],
                        )
                      }
                      onSelectAll={() => setExcludedLectures([])}
                      onDeselectAll={() => setExcludedLectures(playedModes)}
                      labels={{
                        icon: '🎓',
                        unit: 'lecture',
                        heading: 'Use as context',
                        allHint: 'Every played lecture is fed to the researcher.',
                        someHint: 'Only the checked lectures are fed to the researcher.',
                        noneHint: 'No lectures selected — answers ignore them.',
                        buttonTitle: 'Choose which played lectures the researcher uses as context',
                      }}
                    />
                  )}
                  {sourcePicker}
                  {searchControls}
                </div>
              </div>
              <div className="section-body" hidden={!chatOpen}>
                {chatTurns}
                {chat.length === 0 && (
                  <div className="teacher-hint">
                    Ask a question about the papers on the graph — or play a lecture above.
                  </div>
                )}
              </div>
            </section>
          </>
        ) : (
          // No graph: no sections to divide, so the conversation is the panel.
          <>
            {chatTurns}
            {chat.length === 0 &&
              (landing ? (
                <h1 className="landing-greeting">What do you want to explore?</h1>
              ) : (
                <div className="teacher-hint">
                  Ask a question and I’ll answer straight from your uploaded sources — books, PDFs,
                  and pages — citing them by page. No graph needed.
                </div>
              ))}
          </>
        )}
        {(error || searchError) && <div className="teacher-error">{error ?? searchError}</div>}
      </div>

      {hasGraph && pickedCount > 0 && (
        <p className="ask-context-note">
          Scoped to {pickedCount} hand-picked paper{pickedCount > 1 ? 's' : ''} — lectures and
          answers focus on your selection (clear it on the graph to widen).
        </p>
      )}
      {askContextParts.length > 0 && (
        <p className="ask-context-note">Answers also draw on {askContextParts.join(' · ')}.</p>
      )}
      {/* Bar and tool row move as one thing — which is why the FLIP below
          measures this wrapper rather than the form: on the landing surface
          the whole group drops from the optical centre to the bottom on the
          first question, and a row that snapped down while the bar above it
          slid would read as two separate controls. */}
      <div className="ask-dock" ref={askRef}>
        <form className="teacher-ask" data-tour="ask" onSubmit={onAsk}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onInputKeyDown}
            rows={1}
            placeholder={askPlaceholder}
            aria-label="Ask the assistant a question"
          />
          {/* Clear, inside the bar beside the send rather than floating above the
              transcript — same round shape and size, but muted rather than
              accent: it's the destructive one, and it shouldn't compete with the
              control you actually came here to press. Contextual, as it always
              was: with a lecture on screen it clears that instead of the chat,
              which the tooltip says since the icon can't. */}
          {chat.length > 0 && (
            <button
              type="button"
              className="ask-clear"
              onClick={clearChat}
              title="Clear the chat — start a fresh conversation"
              aria-label="Clear chat"
            >
              <ClearGlyph />
            </button>
          )}
          {/* One button, two jobs. While an answer streams it shows the same
              hopping dots the lecture buttons wear — and hovering turns it into a
              stop, so the control that says "working" is also the one that ends
              it. Deliberately not disabled mid-flight: that was the old ellipsis,
              which looked inert and offered no way out of a long run. */}
          <button
            type={asking || searching ? 'button' : 'submit'}
            className={asking ? 'is-stop' : undefined}
            disabled={(!asking && !input.trim()) || searching}
            onClick={asking ? stopAsk : undefined}
            title={asking ? 'Stop generating' : undefined}
            aria-label={asking ? 'Stop generating' : 'Ask'}
          >
            {asking ? (
              <>
                <HopDots />
                <span className="stop-glyph" aria-hidden="true" />
              </>
            ) : searching ? (
              // A direct search is short and has no partial result worth
              // keeping, so it shows progress without offering a stop.
              <HopDots />
            ) : (
              '↑'
            )}
          </button>
        </form>
        {/* No graph means no sections, so the controls that bind the ask have
            nowhere above to live — they sit as a chip row directly beneath the
            bar instead, near what they modify and out of it. Rendered only
            here: with a graph they are up on the Chat row. */}
        {!hasGraph && (
          <div className="ask-tools">
            {sourcePicker}
            {searchControls}
          </div>
        )}
      </div>

      {lightbox && <Lightbox figure={lightbox} onClose={() => setLightbox(null)} />}
    </section>
  )
}
