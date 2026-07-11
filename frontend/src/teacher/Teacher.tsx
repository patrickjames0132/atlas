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
import type { FormEvent } from 'react'
import { listSources, type AnswerFigure, type LectureMode, type Source } from '../api'
import { useAppSelector } from '../store'
import { selectVisibleBeats } from '../store/transcript'
import ScopePicker from './ScopePicker'
import Lightbox from '../figures/Lightbox'
import BeatList from './transcript/BeatList'
import ChatMessage from './transcript/ChatMessage'
import { useConversation } from './useConversation'
import { useResizablePanel } from '../ui/useResizablePanel'
import './teacher.css'

const MODES: { key: LectureMode; label: string }[] = [
  { key: 'history', label: 'How we got here' },
  { key: 'intuition', label: "This paper's intuition" },
  { key: 'evolution', label: 'The landmark papers since' },
  { key: 'frontier', label: 'The current frontier' },
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

  const [input, setInput] = useState('')
  // The uploaded library, powering the source-scope picker. The picker only
  // appears when there's more than one source to pick between.
  const [libraryItems, setLibraryItems] = useState<Source[]>([])
  // Checked = the assistant may search that source. All checked = no scope.
  const [scopeIds, setScopeIds] = useState<string[]>([])
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

  const onAsk = (event: FormEvent) => {
    event.preventDefault()
    const question = input.trim()
    if (!question || asking) return
    setInput('')
    ask(question, scopeArg)
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
            <div className="lecture-grid">
              {MODES.map((mode) => {
                const active = activeMode === mode.key
                const loading = loadingModes.includes(mode.key)
                // The "click to show" dot marks a played-but-hidden lecture;
                // a loading one shows its hopping dots instead.
                const cached = !loading && (lectures[mode.key]?.length ?? 0) > 0
                return (
                  <button
                    key={mode.key}
                    className={`teach-btn${active ? ' active' : ''}${
                      cached && !active ? ' cached' : ''
                    }`}
                    // Lectures load in parallel — every button stays live so
                    // you can show/hide or start another while one generates.
                    onClick={() => toggleLecture(mode.key)}
                    aria-pressed={active}
                    title={
                      loading
                        ? active
                          ? 'Loading… click to hide (keeps loading)'
                          : 'Loading in the background… click to show'
                        : active
                          ? 'Hide this lecture'
                          : cached
                            ? 'Show this lecture'
                            : mode.label
                    }
                  >
                    {loading ? (
                      <span className="hop-dots" aria-label="Loading lecture">
                        <span className="hop-dot" />
                        <span className="hop-dot" />
                        <span className="hop-dot" />
                      </span>
                    ) : (
                      mode.label
                    )}
                  </button>
                )
              })}
            </div>
            <p className="lecture-scope-note">
              Each lecture is grounded in the papers currently shown on the graph — filter the graph
              to narrow what it covers.
            </p>
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
        <BeatList
          beats={beats}
          activeBeat={activeBeat}
          onBeatClick={onBeatClick}
          onRefClick={onRefClick}
          onEnlarge={setLightbox}
        />

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

        {beats.length === 0 && chat.length === 0 && loadingModes.length === 0 && (
          <div className="teacher-hint">
            {hasGraph
              ? 'Play a lecture, or ask a question about the papers on the graph.'
              : 'Ask a question and I’ll answer straight from your uploaded sources — books, PDFs, and pages — citing them by page. No graph needed.'}
          </div>
        )}
        {error && <div className="teacher-error">{error}</div>}
      </div>

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
