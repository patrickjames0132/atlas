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
 * The conversation itself lives in the store (transcript slice) and the
 * stream orchestration in useConversation; this component owns only what it
 * alone renders — the input box, the scope picker's data, the lightbox. A
 * restored session's transcript arrives via the store, no seeding props
 * needed.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, FormEvent, KeyboardEvent } from 'react'
import { LECTURE_TITLES, type AnswerFigure, type LectureMode } from '../api'
import { useAppDispatch, useAppSelector } from '../store'
import { loadLibrary, selectLibrary } from '../store/library'
import { selectVisibleBeats, selectVisibleSourceRefs } from '../store/transcript'
import { REL_COLOR } from '../graph/theme'
import HopDots from './HopDots'
import ScopePicker from './ScopePicker'
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
    clear,
  } = useConversation()

  // Clear is contextual: a shown lecture → clear that lecture; otherwise → clear
  // the chat. Show the button whenever the active context has something to wipe.
  const clearsLecture = activeMode !== null
  const showClear = clearsLecture || chat.length > 0
  // The shown lecture's metadata (name + relation colour), for the transcript's
  // "Now playing" header. null when no lecture is shown (a Q&A chat, or idle).
  const activeModeMeta = MODES.find((mode) => mode.key === activeMode) ?? null

  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  // The uploaded library, powering the source-scope picker (shown at more than
  // one source). Read LIVE from the library slice — the Sources drawer reloads
  // the slice on every upload/delete, so the picker appears the moment a
  // second source lands (it used to sit on a stale mount-time fetch until a
  // page reload).
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
  const [openScope, setOpenScope] = useState<'lectures' | 'sources' | null>(null)
  // The answer figure opened full-screen (null = closed).
  const [lightbox, setLightbox] = useState<AnswerFigure | null>(null)
  const { width, onHandlePointerDown, dragging } = useResizablePanel('atlas.teacherWidth', 340)

  // First reader fetches; the loaded flag keeps the drawer (and the remounts
  // that Home and a session restore still cause) from re-fetching a library
  // the store already holds.
  useEffect(() => {
    if (!libraryLoaded) dispatch(loadLibrary())
  }, [libraryLoaded, dispatch])

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

  const submitQuestion = () => {
    const question = input.trim()
    if (!question || asking) return
    setInput('')
    ask(question, scopeArg, lectureScope)
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
  const askRef = useRef<HTMLFormElement>(null)
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
  const askContextParts: string[] = []
  if (hasGraph && lectureScope.length > 0) {
    askContextParts.push(
      `${lectureScope.length} played lecture${lectureScope.length > 1 ? 's' : ''} (🎓)`,
    )
  }
  if (scopeIds.length > 0) {
    askContextParts.push(`${scopeIds.length} source${scopeIds.length > 1 ? 's' : ''} (📚)`)
  }

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
        {/* The landing surface has no panel title and nothing to close, and
            its source picker moved into the ask bar — so the row would be an
            empty strip of chrome. */}
        {!landing && (
          <div className="teacher-head-top">
            <span className="teacher-title">{hasGraph ? 'AI teacher' : 'Ask the assistant'}</span>
            <div className="teacher-head-right">
              {hasGraph && playedModes.length > 0 && (
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
        {hasGraph && (
          <div className="teacher-modes">
            <p className="lecture-intro">
              Play a lecture to summarize different node types. Each lecture is grounded in the
              papers currently shown on the graph — filter it, or alt-drag on the canvas to
              hand-pick a cluster, to narrow what it covers.
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
                // "Now playing" header above the transcript.
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
          </div>
        )}
      </div>

      <div className="teacher-scroll" ref={scrollRef} onScroll={onTranscriptScroll}>
        {/* One panel, two views: a shown lecture takes over the scroll (its
            "Now playing" header + beats); otherwise it's the Q&A chat. Asking a
            question hides the lecture, so the two never stack on top of each
            other. Both survive the switch — the lecture stays cached, the chat
            stays in the store. */}
        {activeModeMeta ? (
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
        ) : (
          <>
            {chat.map((message, index) => {
              // Clicking the bubble re-lights the answer's whole grounding
              // set — so it's only a control while at least one of those
              // papers is actually on the graph. Since the conversation now
              // outlives the graph it was written against, an older answer can
              // cite nothing that's still loaded, and a clickable bubble that
              // highlights nothing is the same dead pointer its `[n]` chips
              // grey out for. Partial overlap still counts: lighting the
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
                  streaming={asking}
                  onActivate={clickable ? () => onChatClick(index, message.cited!) : undefined}
                  onRefClick={onRefClick}
                  onGraphIds={onGraphIds}
                  onPaperSeed={onPaperSeed}
                  provider={provider}
                  onEnlarge={setLightbox}
                />
              )
            })}
            {chat.length === 0 &&
              (landing ? (
                <h1 className="landing-greeting">What do you want to explore?</h1>
              ) : (
                <div className="teacher-hint">
                  {hasGraph
                    ? 'Ask a question about the papers on the graph — or play a lecture above.'
                    : 'Ask a question and I’ll answer straight from your uploaded sources — books, PDFs, and pages — citing them by page. No graph needed.'}
                </div>
              ))}
          </>
        )}
        {error && <div className="teacher-error">{error}</div>}
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
      <form className="teacher-ask" data-tour="ask" onSubmit={onAsk} ref={askRef}>
        {/* Which sources the researcher may search, inset in the bar rather than
            floating above it: it belongs to the question you're about to ask,
            so it sits with the ask. */}
        {libraryItems.length > 1 && (
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
        )}
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
        {showClear && (
          <button
            type="button"
            className="ask-clear"
            onClick={clear}
            title={
              clearsLecture ? 'Clear this lecture' : 'Clear the chat — start a fresh conversation'
            }
            aria-label={clearsLecture ? 'Clear lecture' : 'Clear chat'}
          >
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
          </button>
        )}
        {/* One button, two jobs. While an answer streams it shows the same
            hopping dots the lecture buttons wear — and hovering turns it into a
            stop, so the control that says "working" is also the one that ends
            it. Deliberately not disabled mid-flight: that was the old ellipsis,
            which looked inert and offered no way out of a long run. */}
        <button
          type={asking ? 'button' : 'submit'}
          className={asking ? 'is-stop' : undefined}
          disabled={!asking && !input.trim()}
          onClick={asking ? stopAsk : undefined}
          title={asking ? 'Stop generating' : undefined}
          aria-label={asking ? 'Stop generating' : 'Ask'}
        >
          {asking ? (
            <>
              <HopDots />
              <span className="stop-glyph" aria-hidden="true" />
            </>
          ) : (
            '↑'
          )}
        </button>
      </form>

      {lightbox && <Lightbox figure={lightbox} onClose={() => setLightbox(null)} />}
    </section>
  )
}
