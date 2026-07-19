/**
 * One chat turn: the library-retrieval summary (graph-free mode), the
 * researcher's trace chips, the prose interleaved with its `<<FIG n>>` figures,
 * and the cited-papers footer. Clickable when the answer carries citations —
 * clicking re-lights the papers it was grounded in.
 */

import type { AnswerFigure, ChatMsg, TraceEvent } from '../../api'
import MathText from '../../notation/MathText'
import FigCard from '../figures/FigCard'
import { splitAnswer } from '../figures/split'
import AnswerMarkdown from './AnswerMarkdown'

/**
 * Why a failed search never turned anything up, in plain words — "the budget
 * ran out" and "Semantic Scholar errored" read very differently to someone
 * watching the trace. Undefined `reason` (older saved sessions, or a passing
 * search) renders nothing extra, same as before this field existed.
 *
 * @param reason The trace's failure-reason code, when one was sent.
 * @returns The plain-words explanation, or null for nothing extra.
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

/**
 * One trace chip: a human line per researcher action, failures included.
 *
 * @returns The rendered trace line.
 */
function TraceLine({ trace }: { trace: TraceEvent }) {
  if (trace.action === 'figure')
    return (
      <div className={`trace-line ${trace.ok ? '' : 'fail'}`}>
        🖼 {trace.ok ? 'Showed' : 'Tried'} <b>{trace.label ?? `Figure ${trace.figure}`}</b>
        {trace.title ? (
          <>
            {' '}
            of <b>{trace.title}</b>
          </>
        ) : null}
      </div>
    )
  if (trace.action === 'search_sources')
    return (
      <div className={`trace-line ${trace.ok ? '' : 'fail'}`}>
        📚 {trace.ok ? 'Searched your sources' : 'Tried your sources'}
        {trace.query ? (
          <>
            {' '}
            for <b>“{trace.query}”</b>
          </>
        ) : null}
        {trace.ok && (
          <em>{trace.found ? `${trace.found} passage${trace.found > 1 ? 's' : ''}` : 'nothing'}</em>
        )}
      </div>
    )
  if (trace.action === 'search')
    return (
      <div className={`trace-line ${trace.ok ? '' : 'fail'}`}>
        🔎 {trace.ok ? 'Searched' : 'Tried'} <b>“{trace.query}”</b>
        {trace.year_from || trace.year_to ? (
          <span>
            {' '}
            ({trace.year_from ?? '…'}–{trace.year_to ?? 'now'})
          </span>
        ) : null}
        {trace.ok && <em>{trace.found ? `${trace.found} new` : 'nothing new'}</em>}
        {!trace.ok && searchFailReason(trace.reason) && <em>{searchFailReason(trace.reason)}</em>}
      </div>
    )
  if (trace.action === 'expand')
    return (
      <div className={`trace-line ${trace.ok ? '' : 'fail'}`}>
        🔗 {trace.ok ? 'Expanded' : 'Tried'} <b>{trace.relation}</b> of{' '}
        <b>{trace.title || `paper #${trace.index}`}</b>
        {trace.ok && <em>{trace.found ? `${trace.found} new` : 'nothing new'}</em>}
      </div>
    )
  return (
    <div className={`trace-line ${trace.ok ? '' : 'fail'}`}>
      📖 {trace.ok ? 'Read' : 'Tried'} <b>{trace.title || `paper #${trace.index}`}</b>
      <em>{trace.detail === 'full' ? 'full text' : 'summary'}</em>
    </div>
  )
}

/**
 * Render one chat turn end-to-end.
 *
 * @returns The turn's bubble (retrieval line, trace chips, prose, figures).
 */
export default function ChatMessage({
  message,
  active,
  streaming,
  onActivate,
  onRefClick,
  onEnlarge,
}: {
  message: ChatMsg
  /** This answer's cited papers are currently lit on the graph. */
  active: boolean
  /** An answer is streaming app-wide (drives the placeholder ellipsis). */
  streaming: boolean
  /** Re-light this answer's cited papers (undefined = not clickable). */
  onActivate?: () => void
  /** Spotlight one paper from a clicked inline `[n]` marker. */
  onRefClick?: (nodeId: string) => void
  onEnlarge: (figure: AnswerFigure) => void
}) {
  const clickable = !!onActivate
  return (
    <div
      className={`chat ${message.role}${clickable ? ' clickable' : ''}${active ? ' active' : ''}`}
      onClick={onActivate}
    >
      {/* Library-chat retrieval summary (graph-free mode). */}
      {message.retrieve && (
        <div className="chat-trace">
          <div className={`trace-line ${message.retrieve.found ? '' : 'fail'}`}>
            📚 Searched your library
            <em>
              {message.retrieve.found
                ? `${message.retrieve.found} passage${message.retrieve.found > 1 ? 's' : ''}`
                : 'nothing'}
            </em>
            {message.retrieve.sources.length > 0 && (
              <span className="trace-srcs"> from {message.retrieve.sources.join(', ')}</span>
            )}
          </div>
        </div>
      )}
      {message.trace && message.trace.length > 0 && (
        <div className="chat-trace">
          {message.trace.map((event, index) => (
            <TraceLine key={index} trace={event} />
          ))}
        </div>
      )}
      {(() => {
        if (!message.text) {
          return message.role === 'assistant' &&
            streaming &&
            !message.trace?.length &&
            !message.retrieve
            ? '…'
            : ''
        }
        // Interleave the prose with the figures the agent placed via
        // <<FIG n>> markers; unplaced figures fall back to the end.
        const { parts, leftover } = splitAnswer(message.text, message.figures)
        return (
          <>
            {parts.map((part, index) =>
              typeof part === 'string' ? (
                message.role === 'assistant' ? (
                  // Agent prose: full Markdown + math + clickable [n] citations.
                  <AnswerMarkdown
                    key={index}
                    text={part}
                    refs={message.refs}
                    onRefClick={onRefClick}
                  />
                ) : (
                  // The user's own question — plain text, math typeset, no Markdown.
                  <span key={index}>
                    <MathText>{part}</MathText>
                  </span>
                )
              ) : (
                <div key={index} className="chat-figs chat-figs-inline">
                  <FigCard figure={part} onEnlarge={onEnlarge} />
                </div>
              ),
            )}
            {leftover.length > 0 && (
              <div className="chat-figs">
                {leftover.map((figure, index) => (
                  <FigCard key={index} figure={figure} onEnlarge={onEnlarge} />
                ))}
              </div>
            )}
          </>
        )
      })()}
      {message.cited && message.cited.length > 0 && (
        <div className="chat-cited">grounded in {message.cited.length} paper(s) ✦</div>
      )}
    </div>
  )
}
