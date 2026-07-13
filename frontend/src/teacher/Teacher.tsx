/**
 * The unified assistant panel — now a slim shell. One docked side panel
 * whose capability levels up with context:
 *   • No graph, has a library → the graph-free library chat (librarian).
 *   • A graph is open → the streaming lecture + agentic Q&A (researcher).
 *
 * The conversation itself lives in the store (transcript slice) and the
 * stream orchestration in useConversation; this component owns only what it
 * alone renders — the input box, the scope picker's data, the lightbox.
 * The panel is remounted per workspace epoch (keyed by the parent), so a
 * re-seed starts a fresh conversation; a restored session's transcript
 * arrives via the store, no seeding props needed.
 */

import { useEffect, useState } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import {
  listSources,
  LECTURE_TITLES,
  type AnswerFigure,
  type LectureMode,
  type Source,
} from '../api'
import { useAppSelector } from '../store'
import { selectVisibleBeats } from '../store/transcript'
import { REL_COLOR } from '../graph/theme'
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
 * Render the assistant panel: lecture buttons, transcript, and the ask form.
 *
 * @returns The docked, resizable assistant panel.
 */
export default function Teacher({
  collapsed = false,
  onClose,
}: {
  /** Hidden (but kept mounted, so the conversation survives) when collapsed. */
  collapsed?: boolean
  /** Collapse the panel (the header ✕). */
  onClose?: () => void
}) {
  const chat = useAppSelector((state) => state.transcript.chat)
  const beats = useAppSelector(selectVisibleBeats)
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
    toggleLecture,
    ask,
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
  // The uploaded library, powering the source-scope picker. The picker only
  // appears when there's more than one source to pick between.
  const [libraryItems, setLibraryItems] = useState<Source[]>([])
  // Checked = the assistant may search that source. All checked = no scope.
  const [scopeIds, setScopeIds] = useState<string[]>([])
  // Lectures the researcher may NOT use as context, tracked by EXCLUSION so a
  // lecture played after the user last touched the picker is fed by default.
  const [excludedLectures, setExcludedLectures] = useState<LectureMode[]>([])
  // The answer figure opened full-screen (null = closed).
  const [lightbox, setLightbox] = useState<AnswerFigure | null>(null)
  const { width, onHandlePointerDown, dragging } = useResizablePanel('atlas.teacherWidth', 340)

  useEffect(() => {
    listSources()
      .then((res) => {
        setLibraryItems(res.sources)
        setScopeIds(res.sources.map((source) => source.id)) // default: every source checked
      })
      .catch(() => {})
  }, [])

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

  const onAsk = (event: FormEvent) => {
    event.preventDefault()
    const question = input.trim()
    if (!question || asking) return
    setInput('')
    ask(question, scopeArg, lectureScope)
  }

  return (
    <section className={`teacher ${collapsed ? 'collapsed' : ''}`} style={{ width }}>
      <div
        className={`panel-resize-handle${dragging ? ' dragging' : ''}`}
        onPointerDown={onHandlePointerDown}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panel"
      />
      <div className="teacher-head">
        <div className="teacher-head-top">
          <span className="teacher-title">{hasGraph ? 'AI teacher' : 'Ask your library'}</span>
          <div className="teacher-head-right">
            {hasGraph && playedModes.length > 0 && (
              <ScopePicker
                items={lectureItems}
                checkedIds={lectureScope}
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
            {libraryItems.length > 1 && (
              <ScopePicker
                items={libraryItems}
                checkedIds={scopeIds}
                onToggle={(id) =>
                  setScopeIds((prev) =>
                    prev.includes(id) ? prev.filter((other) => other !== id) : [...prev, id],
                  )
                }
                onSelectAll={() => setScopeIds(libraryItems.map((source) => source.id))}
                onDeselectAll={() => setScopeIds([])}
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
            {onClose && (
              <button className="link-btn" onClick={onClose} aria-label="Close the assistant panel">
                ✕
              </button>
            )}
          </div>
        </div>
        {hasGraph && (
          <div className="teacher-modes">
            <p className="lecture-intro">
              Play a lecture to summarize different node types. Each lecture is grounded in the
              papers currently shown on the graph — filter it, or alt-drag on the canvas to
              hand-pick a cluster, to narrow what it covers.
            </p>
            <div className="lecture-grid">
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
                    {loading ? (
                      <span className="hop-dots" aria-label="Loading lecture">
                        <span className="hop-dot" />
                        <span className="hop-dot" />
                        <span className="hop-dot" />
                      </span>
                    ) : (
                      mode.tag
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {showClear && (
        <div className="teacher-toolbar">
          <button
            className="clear-btn"
            onClick={clear}
            title={
              clearsLecture
                ? 'Clear this lecture'
                : 'Clear the Q&A chat — start a fresh conversation'
            }
          >
            {clearsLecture ? 'Clear lecture' : 'Clear chat'}
          </button>
        </div>
      )}

      <div className="teacher-scroll">
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
              activeBeat={activeBeat}
              onBeatClick={onBeatClick}
              onRefClick={onRefClick}
              onEnlarge={setLightbox}
            />
            {beats.length === 0 && loadingModes.includes(activeModeMeta.key) && (
              <div className="teacher-hint">Preparing the lecture…</div>
            )}
          </>
        ) : (
          <>
            {chat.map((message, index) => {
              const clickable =
                message.role === 'assistant' && !!message.cited && message.cited.length > 0
              return (
                <ChatMessage
                  key={`c${index}`}
                  message={message}
                  active={activeChat === index}
                  streaming={asking}
                  onActivate={clickable ? () => onChatClick(index, message.cited!) : undefined}
                  onRefClick={onRefClick}
                  onEnlarge={setLightbox}
                />
              )
            })}
            {chat.length === 0 && (
              <div className="teacher-hint">
                {hasGraph
                  ? 'Ask a question about the papers on the graph — or play a lecture above.'
                  : 'Ask a question and I’ll answer straight from your uploaded sources — books, PDFs, and pages — citing them by page. No graph needed.'}
              </div>
            )}
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
      {hasGraph && lectureScope.length > 0 && (
        <p className="ask-context-note">
          Answers also draw on {lectureScope.length} played lecture
          {lectureScope.length > 1 ? 's' : ''} (choose with 🎓 above).
        </p>
      )}
      <form className="teacher-ask" onSubmit={onAsk}>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={hasGraph ? 'Ask about the papers on screen…' : 'Ask your books and PDFs…'}
          aria-label="Ask the assistant a question"
        />
        <button type="submit" disabled={asking || !input.trim()}>
          {asking ? '…' : 'Ask'}
        </button>
      </form>

      {lightbox && <Lightbox figure={lightbox} onClose={() => setLightbox(null)} />}
    </section>
  )
}
