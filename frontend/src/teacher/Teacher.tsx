import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  streamAsk,
  streamLecture,
  type Beat,
  type ChatMsg,
  type Discovery,
  type GraphEdge,
  type GraphNode,
  type GraphResponse,
  type LectureMode,
  type LectureTrace,
  type TeacherNode,
} from '../api'
import './teacher.css'

// The AI teacher panel: a streaming lecture over the visible graph plus a
// grounded, agentic Q&A chat. Both light up graph nodes via `onHighlight` — the
// lecture per-beat, Q&A on the papers an answer cites. The Q&A agent can also
// pull in papers not yet on screen via expand_node; discoveries flow back up
// through `onDiscover` so the parent can merge them into the live graph and
// keep grounding follow-up questions.
//
// The transcript (chat + lecture beats + history trace) is seeded from
// `initial*` props and reported up through `onStateChange`, so the parent can
// persist it with a saved session (Phase 4) and rehydrate it on restore. The
// panel is remounted (keyed on the graph) whenever a new graph loads, so a
// re-seed starts a fresh conversation unless we're restoring a saved one.

const MODES: { key: LectureMode; label: string }[] = [
  { key: 'history', label: 'How we got here' },
  { key: 'intuition', label: "This paper's intuition" },
]

function toTeacherNodes(nodes: GraphNode[]): TeacherNode[] {
  return nodes.map((n) => ({
    id: n.id,
    title: n.title,
    year: n.year,
    citation_count: n.citation_count,
    authors: n.authors,
    tldr: n.tldr,
    abstract: n.abstract,
    rels: n.rels,
  }))
}

export default function Teacher({
  graph,
  extraNodes,
  onHighlight,
  onDiscover,
  onStateChange,
  initialChat = [],
  initialBeats = [],
  initialHistTrace = [],
}: {
  graph: GraphResponse
  extraNodes: GraphNode[] // papers the agent discovered via expand_node, so far
  onHighlight: (ids: Set<string>) => void
  onDiscover: (nodes: GraphNode[], edges: GraphEdge[]) => void
  // Reports the live transcript up so the parent can save it (Phase 4).
  onStateChange?: (s: { chat: ChatMsg[]; beats: Beat[]; histTrace: LectureTrace[] }) => void
  // Seed state — populated when restoring a saved session, empty otherwise.
  initialChat?: ChatMsg[]
  initialBeats?: Beat[]
  initialHistTrace?: LectureTrace[]
}) {
  const [beats, setBeats] = useState<Beat[]>(initialBeats)
  // History-mode backward hops (Phase 3e), shown above the beats as the lecture
  // traces a field back to its roots before narrating.
  const [histTrace, setHistTrace] = useState<LectureTrace[]>(initialHistTrace)
  const [activeBeat, setActiveBeat] = useState<number | null>(null)
  // Which chat answer is "active" (its cited papers lit on the graph) — mirrors
  // activeBeat for lecture beats. Only one of the two is active at a time.
  const [activeChat, setActiveChat] = useState<number | null>(null)
  const [teaching, setTeaching] = useState(false)
  const [chat, setChat] = useState<ChatMsg[]>(initialChat)
  const [input, setInput] = useState('')
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Report the transcript up whenever it changes, so the parent always holds the
  // latest to persist. (Cheap — these arrays are small and change on user turns.)
  useEffect(() => {
    onStateChange?.({ chat, beats, histTrace })
  }, [chat, beats, histTrace, onStateChange])

  const sessionId = useRef(
    (crypto.randomUUID?.() as string) || String(Math.random()).slice(2),
  )
  const abortRef = useRef<AbortController | null>(null)
  // Index of the assistant message the in-flight question is streaming into, so
  // onCited can mark it active (its answer just lit up its cited papers).
  const askIdxRef = useRef(0)
  const seed = useMemo(() => ({ title: graph.seed.title, id: graph.seed.id }), [graph])
  // Grounding scope for the agent: the on-screen graph plus anything it has
  // already discovered this session, so follow-up questions can build on it.
  // Deduped by id — a restored session carries its discovered papers in both
  // graph.nodes and extraNodes, and we don't want them grounded twice.
  const teacherNodes = useMemo(() => {
    const seen = new Set<string>()
    const merged: GraphNode[] = []
    for (const n of [...graph.nodes, ...extraNodes]) {
      if (seen.has(n.id)) continue
      seen.add(n.id)
      merged.push(n)
    }
    return toTeacherNodes(merged)
  }, [graph, extraNodes])

  const stopActive = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  // Wipe the transcript on demand — a fresh conversation without re-seeding the
  // graph. (Re-seeding via "Explore from here" remounts this panel, which also
  // clears it; this is the explicit in-place button.) A new session id detaches
  // follow-ups from the old backend-side history too.
  const clearChat = useCallback(() => {
    stopActive()
    setBeats([])
    setHistTrace([])
    setChat([])
    setActiveBeat(null)
    setActiveChat(null)
    setError(null)
    setTeaching(false)
    setAsking(false)
    onHighlight(new Set())
    sessionId.current =
      (crypto.randomUUID?.() as string) || String(Math.random()).slice(2)
  }, [stopActive, onHighlight])

  const highlightBeat = useCallback(
    (i: number, beat: Beat) => {
      // Click the active beat again to clear it and restore the graph.
      const off = activeBeat === i
      setActiveBeat(off ? null : i)
      setActiveChat(null)
      onHighlight(off ? new Set() : new Set(beat.node_ids))
    },
    [activeBeat, onHighlight],
  )

  // Click a Q&A answer to re-light the papers it was grounded in — the chat
  // analogue of clicking a lecture beat. Click the active one again to clear it.
  const highlightChat = useCallback(
    (i: number, cited: string[]) => {
      const off = activeChat === i
      setActiveChat(off ? null : i)
      setActiveBeat(null)
      onHighlight(off ? new Set() : new Set(cited))
    },
    [activeChat, onHighlight],
  )

  const runLecture = useCallback(
    async (mode: LectureMode) => {
      stopActive()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      setBeats([])
      setHistTrace([])
      setActiveBeat(null)
      setActiveChat(null)
      setError(null)
      setTeaching(true)
      onHighlight(new Set())
      try {
        await streamLecture(
          { seed, nodes: teacherNodes, mode },
          {
            signal: ctrl.signal,
            onBeat: (beat) =>
              setBeats((prev) => {
                const next = [...prev, beat]
                // Light up each beat as it arrives.
                highlightBeat(next.length - 1, beat)
                return next
              }),
            // History mode first walks back through references to the field's
            // roots: show the hops, and merge the ancestors into the live graph.
            onTrace: (t) => setHistTrace((prev) => [...prev, t]),
            onNodes: (d) => onDiscover(d.nodes, d.edges),
            onError: (m) => setError(m),
          },
        )
      } catch (e) {
        if (!ctrl.signal.aborted)
          setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null
        setTeaching(false)
      }
    },
    [teacherNodes, seed, onHighlight, onDiscover, highlightBeat, stopActive],
  )

  const onAsk = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      const q = input.trim()
      if (!q || asking) return
      stopActive()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      setInput('')
      setError(null)
      setAsking(true)
      onHighlight(new Set())
      setActiveBeat(null)
      setActiveChat(null)
      setChat((prev) => {
        // The assistant reply is the second message we append here.
        askIdxRef.current = prev.length + 1
        return [...prev, { role: 'user', text: q }, { role: 'assistant', text: '' }]
      })
      try {
        await streamAsk(
          { question: q, session_id: sessionId.current, seed, nodes: teacherNodes },
          {
            signal: ctrl.signal,
            onToken: (text) =>
              setChat((prev) => {
                const next = [...prev]
                next[next.length - 1] = {
                  ...next[next.length - 1],
                  text: next[next.length - 1].text + text,
                }
                return next
              }),
            onTrace: (t) =>
              setChat((prev) => {
                const next = [...prev]
                const last = next[next.length - 1]
                next[next.length - 1] = { ...last, trace: [...(last.trace ?? []), t] }
                return next
              }),
            onDiscard: () =>
              setChat((prev) => {
                const next = [...prev]
                next[next.length - 1] = { ...next[next.length - 1], text: '' }
                return next
              }),
            onNodes: (d: Discovery) => onDiscover(d.nodes, d.edges),
            onCited: (ids) => {
              onHighlight(new Set(ids))
              // Mark this answer active so its section shows the lit state, just
              // like a beat lights up as it arrives.
              setActiveBeat(null)
              setActiveChat(askIdxRef.current)
              setChat((prev) => {
                const next = [...prev]
                next[next.length - 1] = { ...next[next.length - 1], cited: ids }
                return next
              })
            },
            onError: (m) => setError(m),
          },
        )
      } catch (err) {
        if (!ctrl.signal.aborted)
          setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null
        setAsking(false)
      }
    },
    [input, asking, teacherNodes, seed, onHighlight, onDiscover, stopActive],
  )

  return (
    <section className="teacher">
      <div className="teacher-head">
        <span className="teacher-title">AI teacher</span>
        <div className="teacher-modes">
          {MODES.map((m) => (
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
              onClick={clearChat}
              title="Clear the lecture and chat — start a fresh conversation"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="teacher-scroll">
        {histTrace.length > 0 && (
          <div className="chat-trace hist-trace">
            {histTrace.map((t, i) => (
              <div key={i} className={`trace-line ${t.found ? '' : 'fail'}`}>
                ⏳ Traced back{t.oldest ? <> to <b>{t.oldest}</b></> : null}
                <em>
                  {t.found
                    ? `+${t.found} paper${t.found > 1 ? 's' : ''}`
                    : t.error
                      ? 'rate-limited'
                      : 'nothing older found'}
                </em>
              </div>
            ))}
          </div>
        )}
        {beats.length > 0 && (
          <ol className="beats">
            {beats.map((b, i) => (
              <li
                key={i}
                className={`beat ${activeBeat === i ? 'active' : ''}`}
                onClick={() => highlightBeat(i, b)}
              >
                {b.heading && <div className="beat-heading">{b.heading}</div>}
                <p>{b.text}</p>
                {b.node_ids.length > 0 && (
                  <div className="beat-nodes">
                    {b.node_ids.length} paper{b.node_ids.length > 1 ? 's' : ''} ✦
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}

        {chat.map((m, i) => {
          const clickable = m.role === 'assistant' && !!m.cited && m.cited.length > 0
          return (
          <div
            key={`c${i}`}
            className={`chat ${m.role}${clickable ? ' clickable' : ''}${
              activeChat === i ? ' active' : ''
            }`}
            onClick={clickable ? () => highlightChat(i, m.cited!) : undefined}
          >
            {m.trace && m.trace.length > 0 && (
              <div className="chat-trace">
                {m.trace.map((t, j) =>
                  t.action === 'search_sources' ? (
                    <div key={j} className={`trace-line ${t.ok ? '' : 'fail'}`}>
                      📚 {t.ok ? 'Searched your sources' : 'Tried your sources'}
                      {t.query ? (
                        <>
                          {' '}
                          for <b>“{t.query}”</b>
                        </>
                      ) : null}
                      {t.ok && (
                        <em>{t.found ? `${t.found} passage${t.found > 1 ? 's' : ''}` : 'nothing'}</em>
                      )}
                    </div>
                  ) : t.action === 'search' ? (
                    <div key={j} className={`trace-line ${t.ok ? '' : 'fail'}`}>
                      🔎 {t.ok ? 'Searched' : 'Tried'} <b>“{t.query}”</b>
                      {t.year_from || t.year_to ? (
                        <span> ({t.year_from ?? '…'}–{t.year_to ?? 'now'})</span>
                      ) : null}
                      {t.ok && (
                        <em>{t.found ? `${t.found} new` : 'nothing new'}</em>
                      )}
                    </div>
                  ) : t.action === 'expand' ? (
                    <div key={j} className={`trace-line ${t.ok ? '' : 'fail'}`}>
                      🔗 {t.ok ? 'Expanded' : 'Tried'} <b>{t.relation}</b> of{' '}
                      <b>{t.title || `paper #${t.index}`}</b>
                      {t.ok && (
                        <em>{t.found ? `${t.found} new` : 'nothing new'}</em>
                      )}
                    </div>
                  ) : (
                    <div key={j} className={`trace-line ${t.ok ? '' : 'fail'}`}>
                      📖 {t.ok ? 'Read' : 'Tried'}{' '}
                      <b>{t.title || `paper #${t.index}`}</b>
                      <em>{t.detail === 'full' ? 'full text' : 'summary'}</em>
                    </div>
                  ),
                )}
              </div>
            )}
            {m.text ||
              (m.role === 'assistant' && asking && !m.trace?.length ? '…' : '')}
            {m.cited && m.cited.length > 0 && (
              <div className="chat-cited">grounded in {m.cited.length} paper(s) ✦</div>
            )}
          </div>
          )
        })}

        {beats.length === 0 && chat.length === 0 && !teaching && (
          <div className="teacher-hint">
            Play a lecture, or ask a question about the papers on the graph.
          </div>
        )}
        {error && <div className="teacher-error">{error}</div>}
      </div>

      <form className="teacher-ask" onSubmit={onAsk}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about the papers on screen…"
          aria-label="Ask the teacher a question"
        />
        <button type="submit" disabled={asking || !input.trim()}>
          {asking ? '…' : 'Ask'}
        </button>
      </form>
    </section>
  )
}
