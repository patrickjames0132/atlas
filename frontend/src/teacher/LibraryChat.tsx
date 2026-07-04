import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { listSources, streamAskSources, type RetrieveEvent, type Source } from '../api'
import './teacher.css'
import './library-chat.css'

// Offline library chat (Phase 3d): ask questions answered purely from your own
// uploaded library — no graph, no seed search. A lightweight RAG chat that opens
// as a modal; the backend retrieves passages and answers grounded only in them,
// citing sources inline by page.

type ChatMsg = {
  role: 'user' | 'assistant'
  text: string
  retrieve?: RetrieveEvent // which sources this answer was grounded in
}

export default function LibraryChat({ onClose }: { onClose: () => void }) {
  const [chat, setChat] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Scope retrieval to one uploaded source, or '' for the whole library.
  const [items, setItems] = useState<Source[]>([])
  const [scope, setScope] = useState('')

  useEffect(() => {
    listSources().then((res) => setItems(res.sources)).catch(() => {})
  }, [])

  const sessionId = useRef(
    (crypto.randomUUID?.() as string) || String(Math.random()).slice(2),
  )
  const abortRef = useRef<AbortController | null>(null)

  const onAsk = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      const q = input.trim()
      if (!q || asking) return
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      setInput('')
      setError(null)
      setAsking(true)
      setChat((prev) => [...prev, { role: 'user', text: q }, { role: 'assistant', text: '' }])
      try {
        await streamAskSources(
          { question: q, session_id: sessionId.current, source_id: scope || undefined },
          {
            signal: ctrl.signal,
            onRetrieve: (r) =>
              setChat((prev) => {
                const next = [...prev]
                next[next.length - 1] = { ...next[next.length - 1], retrieve: r }
                return next
              }),
            onToken: (text) =>
              setChat((prev) => {
                const next = [...prev]
                const last = next[next.length - 1]
                next[next.length - 1] = { ...last, text: last.text + text }
                return next
              }),
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
    [input, asking, scope],
  )

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="library-chat" role="dialog" aria-label="Chat with your library">
        <header className="library-chat-head">
          <span>💬 Ask your library</span>
          <div className="library-chat-head-right">
            {items.length > 1 && (
              <select
                className="scope-select"
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                aria-label="Scope to a source"
                title="Search your whole library, or just one source"
              >
                <option value="">All sources</option>
                {items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </select>
            )}
            <button className="link-btn" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </header>

        <div className="library-chat-scroll">
          {chat.length === 0 && !asking && (
            <div className="teacher-hint">
              Ask a question and I'll answer straight from your uploaded sources —
              books, PDFs, and pages — citing them by page. No graph needed.
            </div>
          )}
          {chat.map((m, i) => (
            <div key={i} className={`chat ${m.role}`}>
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
              {m.text || (m.role === 'assistant' && asking ? '…' : '')}
            </div>
          ))}
          {error && <div className="teacher-error">{error}</div>}
        </div>

        <form className="teacher-ask" onSubmit={onAsk}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask your books and PDFs…"
            aria-label="Ask your library a question"
            autoFocus
          />
          <button type="submit" disabled={asking || !input.trim()}>
            {asking ? '…' : 'Ask'}
          </button>
        </form>
      </aside>
    </>
  )
}
