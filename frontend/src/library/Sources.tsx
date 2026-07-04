import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteSource,
  ingestUrl,
  listSources,
  uploadSource,
  type Source,
} from '../api'
import './sources.css'

// The Sources drawer: manage the user's local semantic library — upload PDFs /
// books or paste a URL, list what's loaded, remove sources. The library is
// global and persistent; the AI teacher searches it during Q&A (Phase 3d).

export default function Sources({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [available, setAvailable] = useState(true)
  const [items, setItems] = useState<Source[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<string | null>(null) // label of the in-flight ingest
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    const res = await listSources()
    setAvailable(res.available)
    setItems(res.sources)
    setLoading(false)
  }, [])

  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  const onFile = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (fileRef.current) fileRef.current.value = '' // allow re-picking the same file
      if (!file) return
      setError(null)
      setBusy(file.name)
      try {
        await uploadSource(file)
        await refresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(null)
      }
    },
    [refresh],
  )

  const onAddUrl = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      const u = url.trim()
      if (!u || busy) return
      setError(null)
      setBusy(u)
      try {
        await ingestUrl(u)
        setUrl('')
        await refresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(null)
      }
    },
    [url, busy, refresh],
  )

  const onRemove = useCallback(
    async (id: string) => {
      await deleteSource(id)
      await refresh()
    },
    [refresh],
  )

  if (!open) return null

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="sources-drawer" role="dialog" aria-label="Your sources">
        <header className="sources-head">
          <span>Your sources</span>
          <button className="link-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <p className="sources-blurb">
          Upload a book/PDF or paste a link. It's chunked and embedded{' '}
          <b>locally</b> (nothing leaves your machine), so the teacher can search
          it during Q&amp;A.
        </p>

        {!available && (
          <div className="sources-warn">
            Local embeddings aren't available, so search over your sources is off.
            (Is the embedding model able to load?)
          </div>
        )}

        <div className="sources-add">
          <button
            className="src-btn"
            disabled={!!busy || !available}
            onClick={() => fileRef.current?.click()}
          >
            ⬆ Upload PDF
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf"
            hidden
            onChange={onFile}
          />
          <form className="src-url" onSubmit={onAddUrl}>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="…or paste a URL"
              aria-label="Source URL"
              disabled={!!busy || !available}
            />
            <button className="src-btn" type="submit" disabled={!!busy || !available || !url.trim()}>
              Add
            </button>
          </form>
        </div>

        {busy && (
          <div className="sources-busy">
            Ingesting <b>{busy}</b>… <span className="spin" /> (large books take a
            minute)
          </div>
        )}
        {error && <div className="sources-error">{error}</div>}

        <div className="sources-list">
          {loading && items.length === 0 ? (
            <div className="sources-empty">Loading…</div>
          ) : items.length === 0 ? (
            <div className="sources-empty">No sources yet.</div>
          ) : (
            items.map((s) => (
              <div key={s.id} className="source-row">
                <div className="source-meta">
                  <div className="source-title" title={s.origin || s.title}>
                    {s.kind === 'url' ? '🔗' : '📄'} {s.title}
                  </div>
                  <div className="source-sub">
                    {s.pages ? `${s.pages} pages · ` : ''}
                    {s.n_chunks} passages
                  </div>
                </div>
                <button
                  className="link-btn"
                  onClick={() => onRemove(s.id)}
                  aria-label={`Remove ${s.title}`}
                >
                  Remove
                </button>
              </div>
            ))
          )}
        </div>
      </aside>
    </>
  )
}
