import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  listSources,
  streamAsk,
  streamAskSources,
  streamLecture,
  type AnswerFigure,
  type Beat,
  type ChatMsg,
  type Discovery,
  type GraphEdge,
  type GraphNode,
  type GraphResponse,
  type LectureMode,
  type LectureTrace,
  type RetrieveEvent,
  type Source,
  type TeacherNode,
} from '../api'
import './teacher.css'

// The unified assistant panel: one docked side panel whose capability levels up
// with context.
//   • No graph, has a library → a graph-free RAG chat straight over the user's
//     uploaded sources (streamAskSources): retrieve passages, answer grounded in
//     them, cite by page. Works under both teacher backends (no tool loop).
//   • A graph is open → the streaming lecture + agentic Q&A: the agent reads the
//     visible papers, expands/searches for off-graph work, and can search the
//     user's sources too. Both light up graph nodes via `onHighlight`, and
//     agent discoveries flow up through `onDiscover` to merge into the live graph.
// A source-scope dropdown (shown when the library has >1 source) pins the library
// search to one source in either mode. The transcript is seeded from `initial*`
// and reported up via `onStateChange` so a graph session can be saved/restored.
// The panel is remounted (keyed on the graph) whenever a new graph loads, so a
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
  collapsed = false,
  extraNodes,
  onHighlight,
  onDiscover,
  onClose,
  onStateChange,
  initialChat = [],
  initialBeats = [],
  initialHistTrace = [],
}: {
  // The open graph, or null for the graph-free library-chat mode.
  graph: GraphResponse | null
  // Hidden (but kept mounted, so the conversation survives) when collapsed.
  collapsed?: boolean
  extraNodes: GraphNode[] // papers the agent discovered via expand_node, so far
  onHighlight: (ids: Set<string>) => void
  onDiscover: (nodes: GraphNode[], edges: GraphEdge[]) => void
  // Collapse the panel (the header ✕).
  onClose?: () => void
  // Reports the live transcript up so the parent can save it (Phase 4).
  onStateChange?: (s: { chat: ChatMsg[]; beats: Beat[]; histTrace: LectureTrace[] }) => void
  // Seed state — populated when restoring a saved session, empty otherwise.
  initialChat?: ChatMsg[]
  initialBeats?: Beat[]
  initialHistTrace?: LectureTrace[]
}) {
  const hasGraph = !!graph
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
  // The uploaded library, powering the source-scope selector. Empty until
  // fetched; the selector only appears when there's more than one source to pick
  // between. Scoping bears on the library search in either mode.
  const [libraryItems, setLibraryItems] = useState<Source[]>([])
  // The source ids the assistant may search — a CHECKED box = that source is on.
  // Defaults to every source. All checked = no scope (search everything); a
  // subset = just those; NONE checked = search no sources at all.
  const [scopeIds, setScopeIds] = useState<string[]>([])
  const [scopeOpen, setScopeOpen] = useState(false)
  // "No scope" (search the whole library) only when every source is checked;
  // any other state is sent as an explicit id list (empty = search nothing).
  const scopeAll = libraryItems.length === 0 || scopeIds.length === libraryItems.length
  const scopeArg = scopeAll ? undefined : scopeIds
  // The answer figure opened full-screen in the lightbox (null = closed).
  const [lightbox, setLightbox] = useState<AnswerFigure | null>(null)

  // Close the lightbox on Escape while it's open.
  useEffect(() => {
    if (!lightbox) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightbox(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [lightbox])

  /** Add/remove one source id from the checked set. */
  const toggleScope = (id: string) =>
    setScopeIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  useEffect(() => {
    listSources()
      .then((res) => {
        setLibraryItems(res.sources)
        setScopeIds(res.sources.map((s) => s.id)) // default: every source checked
      })
      .catch(() => {})
  }, [])

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
  // Grounding scope for the agent: the on-screen graph plus anything it has
  // already discovered this session, so follow-up questions can build on it.
  // Deduped by id — a restored session carries its discovered papers in both
  // graph.nodes and extraNodes, and we don't want them grounded twice. Empty in
  // the graph-free mode (the library chat needs no node context).
  const teacherNodes = useMemo(() => {
    if (!graph) return [] as TeacherNode[]
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
      if (!graph) return
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
          { seed: { title: graph.seed.title, id: graph.seed.id }, nodes: teacherNodes, mode },
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
    [graph, teacherNodes, onHighlight, onDiscover, highlightBeat, stopActive],
  )

  // Append the user turn + an empty assistant turn the answer streams into, and
  // return the AbortController driving the request.
  const beginTurn = useCallback((q: string) => {
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
    return ctrl
  }, [stopActive, onHighlight])

  // Append streamed prose to the in-flight assistant message.
  const appendToken = useCallback((text: string) => {
    setChat((prev) => {
      const next = [...prev]
      const last = next[next.length - 1]
      next[next.length - 1] = { ...last, text: last.text + text }
      return next
    })
  }, [])

  const onAsk = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      const q = input.trim()
      if (!q || asking) return
      const ctrl = beginTurn(q)
      try {
        if (graph) {
          // Graph open: the agentic Q&A — reads/expands/searches via tool use.
          await streamAsk(
            {
              question: q,
              session_id: sessionId.current,
              seed: { title: graph.seed.title, id: graph.seed.id },
              nodes: teacherNodes,
              source_ids: scopeArg,
            },
            {
              signal: ctrl.signal,
              onToken: appendToken,
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
              onFigure: (f) =>
                setChat((prev) => {
                  const next = [...prev]
                  const last = next[next.length - 1]
                  next[next.length - 1] = { ...last, figures: [...(last.figures ?? []), f] }
                  return next
                }),
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
        } else {
          // No graph: answer straight from the user's uploaded library.
          await streamAskSources(
            {
              question: q,
              session_id: sessionId.current,
              source_ids: scopeArg,
            },
            {
              signal: ctrl.signal,
              onRetrieve: (r: RetrieveEvent) =>
                setChat((prev) => {
                  const next = [...prev]
                  next[next.length - 1] = { ...next[next.length - 1], retrieve: r }
                  return next
                }),
              onToken: appendToken,
              onError: (m) => setError(m),
            },
          )
        }
      } catch (err) {
        if (!ctrl.signal.aborted)
          setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null
        setAsking(false)
      }
    },
    [input, asking, graph, teacherNodes, scopeArg, beginTurn, appendToken, onHighlight, onDiscover],
  )

  return (
    <section className={`teacher ${collapsed ? 'collapsed' : ''}`}>
      <div className="teacher-head">
        <div className="teacher-head-top">
          <span className="teacher-title">{hasGraph ? 'AI teacher' : 'Ask your library'}</span>
          <div className="teacher-head-right">
            {libraryItems.length > 1 && (
              <div className="scope-wrap">
                <button
                  type="button"
                  className={`scope-btn ${scopeAll ? '' : 'on'}`}
                  onClick={() => setScopeOpen((o) => !o)}
                  title="Choose which of your sources the assistant may search"
                >
                  📚 {scopeAll
                    ? 'All sources'
                    : scopeIds.length === 0
                      ? 'No sources'
                      : `${scopeIds.length} source${scopeIds.length > 1 ? 's' : ''}`}
                </button>
                {scopeOpen && (
                  <div className="scope-pop">
                    <div className="scope-pop-head">
                      <span>Search in</span>
                      <span className="scope-pop-actions">
                        {scopeIds.length < libraryItems.length && (
                          <button
                            className="link-btn"
                            onClick={() => setScopeIds(libraryItems.map((s) => s.id))}
                          >
                            Select all
                          </button>
                        )}
                        {scopeIds.length > 0 && (
                          <button className="link-btn" onClick={() => setScopeIds([])}>
                            Deselect all
                          </button>
                        )}
                      </span>
                    </div>
                    {libraryItems.map((s) => (
                      <label key={s.id} className="scope-item">
                        <input
                          type="checkbox"
                          checked={scopeIds.includes(s.id)}
                          onChange={() => toggleScope(s.id)}
                        />
                        <span className="scope-item-title" title={s.title}>
                          {s.title}
                        </span>
                      </label>
                    ))}
                    <div className="scope-hint">
                      {scopeAll
                        ? 'All sources are searched.'
                        : scopeIds.length === 0
                          ? "No sources selected — the assistant won't search your library."
                          : 'Only the checked sources are searched.'}
                    </div>
                  </div>
                )}
              </div>
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
                onClick={clearChat}
                title="Clear the conversation — start fresh"
              >
                Clear
              </button>
            )}
          </div>
        )}
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
                {m.trace.map((t, j) =>
                  t.action === 'figure' ? (
                    <div key={j} className={`trace-line ${t.ok ? '' : 'fail'}`}>
                      🖼 {t.ok ? 'Showed' : 'Tried'} <b>Figure {t.figure}</b>
                      {t.title ? (
                        <>
                          {' '}
                          of <b>{t.title}</b>
                        </>
                      ) : null}
                    </div>
                  ) : t.action === 'search_sources' ? (
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
              (m.role === 'assistant' && asking && !m.trace?.length && !m.retrieve
                ? '…'
                : '')}
            {m.figures && m.figures.length > 0 && (
              <div className="chat-figs">
                {m.figures.map((f, k) => (
                  <figure key={k} className="chat-fig">
                    <button
                      type="button"
                      className="chat-fig-btn"
                      onClick={() => setLightbox(f)}
                      title="Click to enlarge"
                      aria-label="Enlarge figure"
                    >
                      <img src={f.image} alt={f.caption || 'Figure'} loading="lazy" />
                    </button>
                    <figcaption className="chat-fig-cap">
                      <b>Figure {f.figure}</b>
                      {f.title ? ` · ${f.title}` : ''}
                      {f.caption ? ` — ${f.caption}` : ''}
                    </figcaption>
                  </figure>
                ))}
              </div>
            )}
            {m.cited && m.cited.length > 0 && (
              <div className="chat-cited">grounded in {m.cited.length} paper(s) ✦</div>
            )}
          </div>
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

      {lightbox && (
        <div
          className="fig-lightbox"
          onClick={() => setLightbox(null)}
          role="dialog"
          aria-label="Enlarged figure"
        >
          <button className="fig-lightbox-close" aria-label="Close">
            ✕
          </button>
          <img
            src={lightbox.image}
            alt={lightbox.caption || 'Figure'}
            onClick={(e) => e.stopPropagation()}
          />
          {(lightbox.caption || lightbox.figure) && (
            <div className="fig-lightbox-cap" onClick={(e) => e.stopPropagation()}>
              <b>Figure {lightbox.figure}</b>
              {lightbox.title ? ` · ${lightbox.title}` : ''}
              {lightbox.caption ? ` — ${lightbox.caption}` : ''}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
