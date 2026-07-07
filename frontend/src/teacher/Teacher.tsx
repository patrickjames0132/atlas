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
import { selectTranscript } from '../store/transcript'
import ScopePicker from './ScopePicker'
import Lightbox from './figures/Lightbox'
import BeatList from './transcript/BeatList'
import ChatMessage from './transcript/ChatMessage'
import HistTrace from './transcript/HistTrace'
import { useConversation } from './useConversation'
import './teacher.css'

const MODES: { key: LectureMode; label: string }[] = [
  { key: 'history', label: 'How we got here' },
  { key: 'intuition', label: "This paper's intuition" },
]

export default function Teacher({
  collapsed = false,
  onClose,
}: {
  /** Hidden (but kept mounted, so the conversation survives) when collapsed. */
  collapsed?: boolean
  /** Collapse the panel (the header ✕). */
  onClose?: () => void
}) {
  const { chat, beats, histTrace } = useAppSelector(selectTranscript)
  const {
    hasGraph,
    teaching,
    asking,
    error,
    activeBeat,
    activeChat,
    onBeatClick,
    onChatClick,
    runLecture,
    ask,
    clear,
  } = useConversation()

  const [input, setInput] = useState('')
  // The uploaded library, powering the source-scope picker. The picker only
  // appears when there's more than one source to pick between.
  const [libraryItems, setLibraryItems] = useState<Source[]>([])
  // Checked = the assistant may search that source. All checked = no scope.
  const [scopeIds, setScopeIds] = useState<string[]>([])
  // The answer figure opened full-screen (null = closed).
  const [lightbox, setLightbox] = useState<AnswerFigure | null>(null)

  useEffect(() => {
    listSources()
      .then((res) => {
        setLibraryItems(res.sources)
        setScopeIds(res.sources.map((s) => s.id)) // default: every source checked
      })
      .catch(() => {})
  }, [])

  // "No scope" (search the whole library) only when every source is checked;
  // any other state is sent as an explicit id list (empty = search nothing).
  const scopeAll = libraryItems.length === 0 || scopeIds.length === libraryItems.length
  const scopeArg = scopeAll ? undefined : scopeIds

  const onAsk = (e: FormEvent) => {
    e.preventDefault()
    const q = input.trim()
    if (!q || asking) return
    setInput('')
    ask(q, scopeArg)
  }

  return (
    <section className={`teacher ${collapsed ? 'collapsed' : ''}`}>
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
                    prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
                  )
                }
                onSelectAll={() => setScopeIds(libraryItems.map((s) => s.id))}
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
        {(hasGraph || beats.length > 0 || chat.length > 0) && (
          <div className="teacher-modes">
            {hasGraph &&
              MODES.map((m) => (
                <button
                  key={m.key}
                  className="teach-btn"
                  onClick={() => runLecture(m.key)}
                  disabled={teaching}
                >
                  {teaching ? '…' : m.label}
                </button>
              ))}
            {(beats.length > 0 || chat.length > 0) && (
              <button
                className="teach-btn clear-btn"
                onClick={clear}
                title="Clear the conversation — start fresh"
              >
                Clear
              </button>
            )}
          </div>
        )}
      </div>

      <div className="teacher-scroll">
        <HistTrace trace={histTrace} />
        <BeatList beats={beats} activeBeat={activeBeat} onBeatClick={onBeatClick} />

        {chat.map((m, i) => {
          const clickable = m.role === 'assistant' && !!m.cited && m.cited.length > 0
          return (
            <ChatMessage
              key={`c${i}`}
              message={m}
              active={activeChat === i}
              streaming={asking}
              onActivate={clickable ? () => onChatClick(i, m.cited!) : undefined}
              onEnlarge={setLightbox}
            />
          )
        })}

        {beats.length === 0 && chat.length === 0 && !teaching && (
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
          onChange={(e) => setInput(e.target.value)}
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
