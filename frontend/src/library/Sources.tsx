/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The Sources drawer: manage the user's local semantic library — upload PDFs /
 * books (several at once, embedded in parallel) or paste a URL, list what's
 * loaded, remove sources. The library is global and persistent; the AI teacher
 * searches it during Q&A (Phase 3d). The list itself lives in the library
 * slice — every mutation here re-loads it THROUGH the store, so the teacher
 * panel's source-scope picker updates the moment an upload lands (it used to
 * need a page reload).
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteSource, ingestUrl, uploadSource } from '../api'
import { useAppDispatch, useAppSelector } from '../store'
import { loadLibrary, selectLibrary } from '../store/library'
import './sources.css'

/** One file in an in-flight upload batch, tracked for per-file progress.
 * `pct` is embedding progress 0–1 (undefined until the first progress frame —
 * extraction/chunking happens before the bar starts moving). */
type Upload = { name: string; status: 'ingesting' | 'done' | 'error'; error?: string; pct?: number }

/**
 * Run `worker` over `items` with at most `limit` in flight at once.
 *
 * @param items  The work items.
 * @param limit  The concurrency cap.
 * @param worker Processes one item (called with the item and its index).
 */
async function runPool<Item>(
  items: Item[],
  limit: number,
  worker: (item: Item, index: number) => Promise<void>,
): Promise<void> {
  let next = 0
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next++
      await worker(items[index], index)
    }
  })
  await Promise.all(runners)
}

/**
 * Render the Sources drawer: upload/paste, per-file progress, the source list.
 *
 * @returns The drawer, or null while closed.
 */
export default function Sources({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dispatch = useAppDispatch()
  const { available, sources: items, loading } = useAppSelector(selectLibrary)
  const [busy, setBusy] = useState<string | null>(null) // label of the in-flight URL ingest
  const [busyPct, setBusyPct] = useState<number | null>(null) // its embedding progress (0-1)
  // Per-file progress for a multi-file upload batch (parallel, capped).
  const [uploads, setUploads] = useState<Upload[]>([])
  const [dragging, setDragging] = useState(false)
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const uploading = uploads.some((upload) => upload.status === 'ingesting')
  const locked = !!busy || uploading || !available

  const refresh = useCallback(async () => {
    await dispatch(loadLibrary())
  }, [dispatch])

  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  // Ingest a batch of PDFs in parallel (capped), tracking each file's progress.
  // Succeeded rows drop out once they land in the list below; failures linger so
  // the user sees which file broke and why.
  const onFiles = useCallback(
    async (files: File[]) => {
      const pdfs = files.filter(
        (file) => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'),
      )
      if (!pdfs.length || uploading) return
      setError(null)
      setUploads(pdfs.map((file) => ({ name: file.name, status: 'ingesting' })))
      await runPool(pdfs, 3, async (file, index) => {
        try {
          await uploadSource(file, undefined, (progress) =>
            setUploads((prev) =>
              prev.map((upload, position) =>
                position === index
                  ? { ...upload, pct: progress.total ? progress.done / progress.total : 0 }
                  : upload,
              ),
            ),
          )
          setUploads((prev) =>
            prev.map((upload, position) =>
              position === index ? { ...upload, status: 'done' } : upload,
            ),
          )
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err)
          setUploads((prev) =>
            prev.map((upload, position) =>
              position === index ? { ...upload, status: 'error', error: msg } : upload,
            ),
          )
        }
      })
      await refresh()
      setUploads((prev) => prev.filter((upload) => upload.status === 'error'))
    },
    [refresh, uploading],
  )

  const onPick = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = event.target.files ? Array.from(event.target.files) : []
      if (fileRef.current) fileRef.current.value = '' // allow re-picking the same file(s)
      onFiles(files)
    },
    [onFiles],
  )

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      setDragging(false)
      if (locked) return
      onFiles(Array.from(event.dataTransfer.files))
    },
    [locked, onFiles],
  )

  const onAddUrl = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault()
      const trimmedUrl = url.trim()
      if (!trimmedUrl || locked) return
      setError(null)
      setBusy(trimmedUrl)
      setBusyPct(null)
      try {
        await ingestUrl(trimmedUrl, undefined, (progress) =>
          setBusyPct(progress.total ? progress.done / progress.total : 0),
        )
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
      <aside
        className="sources-drawer"
        data-tour="library-panel"
        role="dialog"
        aria-label="Your library"
      >
        <header className="sources-head">
          <span>Your library</span>
          <button className="link-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <p className="sources-blurb">
          Upload a book/PDF or paste a link. It's chunked and embedded <b>locally</b> (nothing
          leaves your machine), so the teacher can search it during Q&amp;A.
        </p>

        {!available && (
          <div className="sources-warn">
            Local embeddings aren't available, so search over your sources is off. (Is the embedding
            model able to load?)
          </div>
        )}

        <div
          className={`sources-add ${dragging ? 'dragging' : ''}`}
          onDragOver={(event) => {
            event.preventDefault()
            if (!locked) setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <button className="src-btn" disabled={locked} onClick={() => fileRef.current?.click()}>
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
              onChange={(event) => setUrl(event.target.value)}
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
            {uploads.map((upload, index) => (
              <div key={index} className={`upload-row ${upload.status}`}>
                <span className="upload-name" title={upload.name}>
                  {upload.name}
                </span>
                <span className="upload-status">
                  {upload.status === 'ingesting' ? (
                    <>
                      <span className="spin" />{' '}
                      {upload.pct != null
                        ? `embedding ${Math.round(upload.pct * 100)}%`
                        : 'reading…'}
                    </>
                  ) : upload.status === 'done' ? (
                    '✓ added'
                  ) : (
                    '✕ failed'
                  )}
                </span>
                {upload.status === 'ingesting' && (
                  <div className="upload-bar">
                    <div
                      className="upload-bar-fill"
                      style={{ width: `${Math.round((upload.pct ?? 0) * 100)}%` }}
                    />
                  </div>
                )}
                {upload.status === 'error' && upload.error && (
                  <div className="upload-err">{upload.error}</div>
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
            items.map((source) => (
              <div key={source.id} className="source-row">
                <div className="source-meta">
                  <div className="source-title" title={source.origin || source.title}>
                    {source.kind === 'url' ? '🔗' : '📄'} {source.title}
                  </div>
                  <div className="source-sub">
                    {source.pages ? `${source.pages} pages · ` : ''}
                    {source.n_chunks} passages
                  </div>
                </div>
                <button
                  className="link-btn"
                  onClick={() => onRemove(source.id)}
                  aria-label={`Remove ${source.title}`}
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
