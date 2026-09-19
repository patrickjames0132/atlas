/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * One chat turn: the library-retrieval summary (graph-free mode), the
 * researcher's trace chips, the prose interleaved with its `<<FIG n>>` figures,
 * and the cited-papers footer. Clickable when the answer carries citations —
 * clicking re-lights the papers it was grounded in.
 *
 * Since v7.20.0 a turn's answer may be a **lecture** rather than prose — the
 * router sent the message to the lecturer — in which case the same `BeatList`
 * the panel's lecture section uses renders here instead, under a line naming
 * which assistant answered and offering the other.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useEffect, useRef, useState } from 'react'
import { PROVIDER_LABEL } from '../../api'
import type { AnswerFigure, Beat, ChatMsg, Provider, TraceEvent } from '../../api'
import MathText from '../../notation/MathText'
import FigCard from '../figures/FigCard'
import HopDots from '../HopDots'
import { splitAnswer } from '../figures/split'
import AnswerMarkdown from './AnswerMarkdown'
import BeatList from './BeatList'
import { provenanceLine } from './provenance'
import { describeScope } from '../../scope/resolve'

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
  if (trace.action === 'search_web')
    return (
      <div className={`trace-line ${trace.ok ? '' : 'fail'}${trace.pending ? ' pending' : ''}`}>
        🌐 {trace.pending ? 'Searching the web' : trace.ok ? 'Searched the web' : 'Tried the web'}
        {trace.need ? (
          <>
            {' '}
            for <b>“{trace.need}”</b>
          </>
        ) : null}
        {trace.pending ? (
          <span className="spin trace-spin" role="img" aria-label="Searching" />
        ) : (
          trace.ok && (
            <em>{trace.found ? `${trace.found} page${trace.found > 1 ? 's' : ''}` : 'nothing'}</em>
          )
        )}
      </div>
    )
  if (trace.action === 'search') {
    // "Searching OpenAlex for …" names the corpus while it runs, then
    // "Searched OpenAlex for …" once it has. The name comes off the event,
    // never the dropdown: a turn saved under one provider and replayed under
    // the other still says where it looked. Turns from before the field
    // existed have no name to give and read as they always did.
    const corpus = trace.provider ? PROVIDER_LABEL[trace.provider] : null
    const verb = trace.pending ? 'Searching' : trace.ok ? 'Searched' : 'Tried'
    return (
      <div className={`trace-line ${trace.ok ? '' : 'fail'}${trace.pending ? ' pending' : ''}`}>
        🔎 {corpus ? `${verb} ${corpus} for` : trace.pending ? 'Searching for' : verb}{' '}
        <b>“{trace.query}”</b>
        {trace.year_from || trace.year_to ? (
          <span>
            {' '}
            ({trace.year_from ?? '…'}–{trace.year_to ?? 'now'})
          </span>
        ) : null}
        {trace.pending && <span className="spin trace-spin" role="img" aria-label="Searching" />}
        {!trace.pending && trace.ok && (
          <em>{trace.found ? `${trace.found} new` : 'nothing new'}</em>
        )}
        {!trace.ok && searchFailReason(trace.reason) && <em>{searchFailReason(trace.reason)}</em>}
      </div>
    )
  }
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
 * The agent's tool trace, collapsible, and self-collapsing when it finishes.
 *
 * Watching the agent work is the interesting part *while it works*; once the
 * answer is there the trace is a wall of chips above the thing the reader
 * actually came for. So it opens on its own when a run starts and folds away
 * when the run ends — and a reader who wants it back (or wants it gone early)
 * has the caret.
 *
 * **A reader's own click wins.** Once they have opened or closed it by hand,
 * the automatic collapse stops fighting them for the rest of that turn: the
 * point of the affordance is to be in control of it.
 *
 * @param trace   The steps to show.
 * @param working This turn's agent is still running.
 * @returns The collapsible trace block.
 */
function TraceBlock({ trace, working }: { trace: TraceEvent[]; working: boolean }) {
  const [open, setOpen] = useState(working)
  const chosenByReader = useRef(false)
  useEffect(() => {
    if (!chosenByReader.current) setOpen(working)
  }, [working])
  const steps = trace.length
  return (
    <div className={`chat-trace${open ? '' : ' collapsed'}`}>
      <button
        type="button"
        className="trace-toggle"
        aria-expanded={open}
        onClick={(event) => {
          // The bubble itself re-lights this answer's papers; toggling the
          // trace is not that.
          event.stopPropagation()
          chosenByReader.current = true
          setOpen((prev) => !prev)
        }}
      >
        <span className={`trace-caret${open ? ' open' : ''}`} aria-hidden="true">
          ▸
        </span>
        {working ? 'Working' : `${steps} step${steps > 1 ? 's' : ''}`}
      </button>
      {open && (
        <div className="trace-steps">
          {trace.map((event, index) => (
            <TraceLine key={index} trace={event} />
          ))}
        </div>
      )}
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
  working,
  onActivate,
  onRetry,
  onRefClick,
  onPaperSeed,
  onThreadOpen,
  provider,
  onEnlarge,
  activeBeat,
  onBeatClick,
  onReroute,
  // Defaults open: a caller that forgets to manage this shows the lecture
  // rather than silently hiding it, which is the right way round to fail.
  beatsOpen = true,
  onToggleBeats,
}: {
  message: ChatMsg
  /** This answer's cited papers are currently lit on the graph. */
  active: boolean
  /** An answer is streaming app-wide (drives the placeholder ellipsis). */
  streaming: boolean
  /** THIS turn's agent is still running — drives the trace's auto-collapse. */
  working?: boolean
  /** Re-light this answer's cited papers (undefined = not clickable). */
  onActivate?: () => void
  /** Ask this turn's question again (undefined = retry unavailable). */
  onRetry?: () => void
  /** Spotlight one paper from a clicked inline `[n]` marker. */
  onRefClick?: (nodeId: string) => void
  /** Paper ids still on the graph; a `[n]` outside it greys out. */
  /** Build a graph seeded on a cited paper (graph-free answers only). */
  onThreadOpen?: (id: string) => void
  onPaperSeed?: (nodeId: string, refProvider?: Provider) => void
  /** The selected backend, so a citation from the other one says so. */
  provider?: Provider
  onEnlarge: (figure: AnswerFigure) => void
  /** Which of this turn's beats is lit, when its answer is a lecture. */
  activeBeat?: number | null
  /** Light one of this turn's beats (undefined = beats render unclickable). */
  onBeatClick?: (index: number, beat: Beat) => void
  /** Send this turn's question to the other assistant — only wired when a
   *  model chose this one, so a reader's own choice carries no offer. */
  onReroute?: () => void
  /** The seed of the graph currently on screen, so a turn from another one can
   *  say which. Undefined graph-free, where nothing is on screen to differ. */
  /** Whether this turn's beats are expanded. */
  beatsOpen?: boolean
  /** Fold or unfold this turn's beats (undefined = not a lecture turn). */
  onToggleBeats?: () => void
}) {
  const clickable = !!onActivate
  const beats = message.beats ?? []
  return (
    <div
      className={`chat ${message.role}${clickable ? ' clickable' : ''}${active ? ' active' : ''}`}
      onClick={onActivate}
    >
      {!!message.borrowedThreads?.length && (
        <div className="chat-borrowed">
          Context from{' '}
          {message.borrowedThreads.map((thread) =>
            onThreadOpen ? (
              <button
                type="button"
                key={thread.id}
                onClick={(event) => {
                  event.stopPropagation()
                  onThreadOpen(thread.id)
                }}
              >
                {thread.title}
              </button>
            ) : (
              <span key={thread.id}>{thread.title}</span>
            ),
          )}
        </div>
      )}
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
        <TraceBlock trace={message.trace} working={!!working} />
      )}
      {message.failed && !message.text && (
        <div className="chat-failed" role="status">
          <span className="chat-failed-msg">⚠ {message.failed}</span>
          {onRetry && (
            <button
              type="button"
              className="chat-retry"
              onClick={(event) => {
                event.stopPropagation()
                onRetry()
              }}
            >
              Try again
            </button>
          )}
        </div>
      )}
      {(() => {
        // What the turn was scoped to, when that was anything other than
        // "what you were looking at": the message's ask ("the references,
        // 2010–2019 · 12 papers") or the hand-picked selection. The one
        // place the priority list is visible in the transcript, so a reader
        // can tell why an answer covered what it did — and why a filtered-out
        // paper turned up anyway.
        const scoped = message.scope ? describeScope(message.scope) : null
        return scoped ? <div className="chat-scoped">Scoped to {scoped}</div> : null
      })()}
      {message.routedTo && (
        // Which assistant answered, and the offer of the other. This line is
        // what makes routing by model acceptable at all: a misroute costs one
        // click rather than a wrong answer the reader has to notice and work
        // around. It is absent when the reader chose the destination
        // themselves, because there is then nothing to second-guess.
        <div className="chat-routed">
          <span>
            {message.routedTo === 'lecture' ? 'Answered as a lecture' : 'Answered as a question'}
          </span>
          {onReroute && (
            <button
              type="button"
              className="chat-reroute"
              onClick={(event) => {
                event.stopPropagation()
                onReroute()
              }}
              title={
                message.routedTo === 'lecture'
                  ? 'Ask this as a question instead'
                  : 'Ask for a lecture on this instead'
              }
            >
              {message.routedTo === 'lecture' ? 'Answer it instead' : 'Lecture on it instead'}
            </button>
          )}
        </div>
      )}
      {beats.length > 0 && (
        // A lecture delivered as this answer, behind its own caret. Twelve
        // beats are fine as the newest thing on screen and unusable as the
        // third lecture you have scrolled past — and the Lecture section that
        // could once fold them away is gone (v7.21.0), so the turn folds
        // itself. Which one is open is decided by the caller: the newest
        // lecture, until the reader says otherwise.
        <div className="chat-beats" onClick={(event) => event.stopPropagation()}>
          <button
            type="button"
            className={`beats-toggle${beatsOpen ? ' open' : ''}`}
            onClick={onToggleBeats}
            aria-expanded={!!beatsOpen}
            title={beatsOpen ? 'Fold this lecture away' : 'Show this lecture'}
          >
            <span className="beats-caret" aria-hidden="true">
              ▸
            </span>
            {beats.length} beat{beats.length > 1 ? 's' : ''}
          </button>
          {/* `hidden` rather than unmounted: a folded lecture keeps its beats'
              figures loaded, so unfolding it is instant rather than a flash of
              re-fetched images. */}
          <div hidden={!beatsOpen}>
            <BeatList
              beats={beats}
              activeBeat={activeBeat ?? null}
              sourceRefs={message.sourceRefs}
              onBeatClick={(index, beat) => onBeatClick?.(index, beat)}
              onRefClick={onRefClick}
              onEnlarge={onEnlarge}
            />
          </div>
        </div>
      )}
      {(() => {
        if (!message.text) {
          // Waiting on the first token, with nothing else yet to show. The
          // same hopping dots the send button and a generating lecture use —
          // one "working" rhythm across the panel, rather than a static `…`
          // here and a cascade everywhere else.
          return message.role === 'assistant' &&
            streaming &&
            !message.failed &&
            !message.trace?.length &&
            !message.retrieve &&
            beats.length === 0 ? (
            <HopDots label="Thinking" />
          ) : (
            ''
          )
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
                    graphRefs={message.graphRefs}
                    sourceRefs={message.sourceRefs}
                    paperRefs={message.paperRefs}
                    onRefClick={onRefClick}
                    onPaperSeed={onPaperSeed}
                    provider={provider}
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
      {(() => {
        // The grounding line replaces the old cited-papers footer: same job,
        // but it counts what the answer actually cited (sources included) and
        // is honest when nothing grounded it. Old saves have no provenance —
        // fall back to the footer they were rendered with.
        // A lecture has no `provenance` — the backend's record counts tool
        // calls, and a lecture makes none. Its own grounding line comes from
        // the scope it narrated, which is the honest equivalent: an answer
        // says what it cited, a lecture says what it covered. The two use the
        // same class so they read alike.
        if (beats.length > 0) {
          return message.graph ? (
            <div className="chat-cited">narrated {message.graph.nodes} papers ✦</div>
          ) : null
        }
        if (!message.provenance) {
          return message.cited && message.cited.length > 0 ? (
            <div className="chat-cited">grounded in {message.cited.length} paper(s) ✦</div>
          ) : null
        }
        const line = provenanceLine(message.provenance)
        return line ? <div className="chat-cited">{line} ✦</div> : null
      })()}
    </div>
  )
}
