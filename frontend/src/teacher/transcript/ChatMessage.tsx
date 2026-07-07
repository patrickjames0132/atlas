/**
 * One chat turn: the library-retrieval summary (graph-free mode), the
 * researcher's trace chips, the prose interleaved with its `<<FIG n>>` figures,
 * and the cited-papers footer. Clickable when the answer carries citations —
 * clicking re-lights the papers it was grounded in.
 */

import type { AnswerFigure, ChatMsg, TraceEvent } from '../../api'
import FigCard from '../figures/FigCard'
import { splitAnswer } from '../figures/split'

/**
 * Why a failed search never turned anything up, in plain words — "the budget
 * ran out" and "Semantic Scholar errored" read very differently to someone
 * watching the trace. Undefined `reason` (older saved sessions, or a passing
 * search) renders nothing extra, same as before this field existed.
 */
function searchFailReason(reason: TraceEvent['reason']): string | null {
  switch (reason) {
    case 'budget_exhausted':
      return 'search budget used up'
    case 'steps_exhausted':
      return 'out of steps'
    case 'empty_query':
      return 'empty query'
    case 'error':
      return 'search failed'
    default:
      return null
  }
}

/** One trace chip: a human line per researcher action, failures included. */
function TraceLine({ t }: { t: TraceEvent }) {
  if (t.action === 'figure')
    return (
      <div className={`trace-line ${t.ok ? '' : 'fail'}`}>
        🖼 {t.ok ? 'Showed' : 'Tried'} <b>Figure {t.figure}</b>
        {t.title ? (
          <>
            {' '}
            of <b>{t.title}</b>
          </>
        ) : null}
      </div>
    )
  if (t.action === 'search_sources')
    return (
      <div className={`trace-line ${t.ok ? '' : 'fail'}`}>
        📚 {t.ok ? 'Searched your sources' : 'Tried your sources'}
        {t.query ? (
          <>
            {' '}
            for <b>“{t.query}”</b>
          </>
        ) : null}
        {t.ok && <em>{t.found ? `${t.found} passage${t.found > 1 ? 's' : ''}` : 'nothing'}</em>}
      </div>
    )
  if (t.action === 'search')
    return (
      <div className={`trace-line ${t.ok ? '' : 'fail'}`}>
        🔎 {t.ok ? 'Searched' : 'Tried'} <b>“{t.query}”</b>
        {t.year_from || t.year_to ? (
          <span>
            {' '}
            ({t.year_from ?? '…'}–{t.year_to ?? 'now'})
          </span>
        ) : null}
        {t.ok && <em>{t.found ? `${t.found} new` : 'nothing new'}</em>}
        {!t.ok && searchFailReason(t.reason) && <em>{searchFailReason(t.reason)}</em>}
      </div>
    )
  if (t.action === 'expand')
    return (
      <div className={`trace-line ${t.ok ? '' : 'fail'}`}>
        🔗 {t.ok ? 'Expanded' : 'Tried'} <b>{t.relation}</b> of{' '}
        <b>{t.title || `paper #${t.index}`}</b>
        {t.ok && <em>{t.found ? `${t.found} new` : 'nothing new'}</em>}
      </div>
    )
  return (
    <div className={`trace-line ${t.ok ? '' : 'fail'}`}>
      📖 {t.ok ? 'Read' : 'Tried'} <b>{t.title || `paper #${t.index}`}</b>
      <em>{t.detail === 'full' ? 'full text' : 'summary'}</em>
    </div>
  )
}

export default function ChatMessage({
  message,
  active,
  streaming,
  onActivate,
  onEnlarge,
}: {
  message: ChatMsg
  /** This answer's cited papers are currently lit on the graph. */
  active: boolean
  /** An answer is streaming app-wide (drives the placeholder ellipsis). */
  streaming: boolean
  /** Re-light this answer's cited papers (undefined = not clickable). */
  onActivate?: () => void
  onEnlarge: (f: AnswerFigure) => void
}) {
  const m = message
  const clickable = !!onActivate
  return (
    <div
      className={`chat ${m.role}${clickable ? ' clickable' : ''}${active ? ' active' : ''}`}
      onClick={onActivate}
    >
      {/* Library-chat retrieval summary (graph-free mode). */}
      {m.retrieve && (
        <div className="chat-trace">
          <div className={`trace-line ${m.retrieve.found ? '' : 'fail'}`}>
            📚 Searched your library
            <em>
              {m.retrieve.found
                ? `${m.retrieve.found} passage${m.retrieve.found > 1 ? 's' : ''}`
                : 'nothing'}
            </em>
            {m.retrieve.sources.length > 0 && (
              <span className="trace-srcs"> from {m.retrieve.sources.join(', ')}</span>
            )}
          </div>
        </div>
      )}
      {m.trace && m.trace.length > 0 && (
        <div className="chat-trace">
          {m.trace.map((t, j) => (
            <TraceLine key={j} t={t} />
          ))}
        </div>
      )}
      {(() => {
        if (!m.text) {
          return m.role === 'assistant' && streaming && !m.trace?.length && !m.retrieve
            ? '…'
            : ''
        }
        // Interleave the prose with the figures the agent placed via
        // <<FIG n>> markers; unplaced figures fall back to the end.
        const { parts, leftover } = splitAnswer(m.text, m.figures)
        return (
          <>
            {parts.map((p, k) =>
              typeof p === 'string' ? (
                <span key={k}>{p}</span>
              ) : (
                <div key={k} className="chat-figs chat-figs-inline">
                  <FigCard f={p} onEnlarge={onEnlarge} />
                </div>
              ),
            )}
            {leftover.length > 0 && (
              <div className="chat-figs">
                {leftover.map((f, k) => (
                  <FigCard key={k} f={f} onEnlarge={onEnlarge} />
                ))}
              </div>
            )}
          </>
        )
      })()}
      {m.cited && m.cited.length > 0 && (
        <div className="chat-cited">grounded in {m.cited.length} paper(s) ✦</div>
      )}
    </div>
  )
}
