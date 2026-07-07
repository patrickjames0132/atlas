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
// books (several at once, embedded in parallel) or paste a URL, list what's
// loaded, remove sources. The library is global and persistent; the AI teacher
// searches it during Q&A (Phase 3d).

/** One file in an in-flight upload batch, tracked for per-file progress.
 * `pct` is embedding progress 0–1 (undefined until the first progress frame —
 * extraction/chunking happens before the bar starts moving). */
type Upload = { name: string; status: 'ingesting' | 'done' | 'error'; error?: string; pct?: number }

/** Run `worker` over `items` with at most `limit` in flight at once. */
async function runPool<T>(
  items: T[],
  limit: number,
  worker: (item: T, index: number) => Promise<void>,
): Promise<void> {
  let next = 0
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const i = next++
      await worker(items[i], i)
    }
  })
  await Promise.all(runners)
}

export default function Sources({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [available, setAvailable] = useState(true)
  const [items, setItems] = useState<Source[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<string | null>(null) // label of the in-flight URL ingest
  const [busyPct, setBusyPct] = useState<number | null>(null) // its embedding progress (0-1)
  // Per-file progress for a multi-file upload batch (parallel, capped).
  const [uploads, setUploads] = useState<Upload[]>([])
  const [dragging, setDragging] = useState(false)
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const uploading = uploads.some((u) => u.status === 'ingesting')
  const locked = !!busy || uploading || !available

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

  // Ingest a batch of PDFs in parallel (capped), tracking each file's progress.
  // Succeeded rows drop out once they land in the list below; failures linger so
  // the user sees which file broke and why.
  const onFiles = useCallback(
    async (files: File[]) => {
      const pdfs = files.filter(
        (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'),
      )
      if (!pdfs.length || uploading) return
      setError(null)
      setUploads(pdfs.map((f) => ({ name: f.name, status: 'ingesting' })))
      await runPool(pdfs, 3, async (file, i) => {
        try {
          await uploadSource(file, undefined, (p) =>
            setUploads((prev) =>
              prev.map((u, j) => (j === i ? { ...u, pct: p.total ? p.done / p.total : 0 } : u)),
            ),
          )
          setUploads((prev) => prev.map((u, j) => (j === i ? { ...u, status: 'done' } : u)))
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err)
          setUploads((prev) =>
            prev.map((u, j) => (j === i ? { ...u, status: 'error', error: msg } : u)),
          )
        }
      })
      await refresh()
      setUploads((prev) => prev.filter((u) => u.status === 'error'))
    },
    [refresh, uploading],
  )

  const onPick = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files ? Array.from(e.target.files) : []
      if (fileRef.current) fileRef.current.value = '' // allow re-picking the same file(s)
      onFiles(files)
    },
    [onFiles],
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      if (locked) return
      onFiles(Array.from(e.dataTransfer.files))
    },
    [locked, onFiles],
  )

  const onAddUrl = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      const u = url.trim()
      if (!u || locked) return
      setError(null)
      setBusy(u)
      setBusyPct(null)
      try {
        await ingestUrl(u, undefined, (p) => setBusyPct(p.total ? p.done / p.total : 0))
        setUrl('')
        await refresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(null)
        setBusyPct(null)
      }
    },
    [url, locked, refresh],
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

        <div
          className={`sources-add ${dragging ? 'dragging' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            if (!locked) setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <button
            className="src-btn"
            disabled={locked}
            onClick={() => fileRef.current?.click()}
          >
            ⬆ Upload PDFs
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            hidden
            onChange={onPick}
          />
          <form className="src-url" onSubmit={onAddUrl}>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="…or paste a URL"
              aria-label="Source URL"
              disabled={locked}
            />
            <button className="src-btn" type="submit" disabled={locked || !url.trim()}>
              Add
            </button>
          </form>
          <div className="drop-hint">Pick several at once, or drop PDFs here</div>
        </div>

        {uploads.length > 0 && (
          <div className="upload-list">
            {uploads.map((u, i) => (
              <div key={i} className={`upload-row ${u.status}`}>
                <span className="upload-name" title={u.name}>
                  {u.name}
                </span>
                <span className="upload-status">
                  {u.status === 'ingesting' ? (
                    <>
                      <span className="spin" />{' '}
                      {u.pct != null ? `embedding ${Math.round(u.pct * 100)}%` : 'reading…'}
                    </>
                  ) : u.status === 'done' ? (
                    '✓ added'
                  ) : (
                    '✕ failed'
                  )}
                </span>
                {u.status === 'ingesting' && (
                  <div className="upload-bar">
                    <div
                      className="upload-bar-fill"
                      style={{ width: `${Math.round((u.pct ?? 0) * 100)}%` }}
                    />
                  </div>
                )}
                {u.status === 'error' && u.error && (
                  <div className="upload-err">{u.error}</div>
                )}
              </div>
            ))}
          </div>
        )}

        {busy && (
          <div className="sources-busy">
            Ingesting <b>{busy}</b>… <span className="spin" />{' '}
            {busyPct != null && `${Math.round(busyPct * 100)}%`}
            <div className="upload-bar">
              <div
                className="upload-bar-fill"
                style={{ width: `${Math.round((busyPct ?? 0) * 100)}%` }}
              />
            </div>
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
