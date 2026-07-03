/**
 * Bring-your-own sources: the user's local semantic library (Phase 3d).
 *
 * Sources are PDFs or web pages ingested server-side (chunked + embedded into
 * a sqlite-vec index) that the teacher can semantically search.
 */

/** One ingested source in the library. */
export interface Source {
  id: string
  title: string
  kind: 'pdf' | 'url'
  /** Where it came from: the original filename or URL. */
  origin: string | null
  /** Page count (PDFs only). */
  pages: number | null
  /** How many chunks it was split into for the vector index. */
  n_chunks: number
  created_at: string
}

/** The `/api/sources` list response. */
export interface SourcesResponse {
  /** Local embeddings + sqlite-vec loaded — false disables the whole feature. */
  available: boolean
  sources: Source[]
}

/**
 * List the user's uploaded sources.
 *
 * Never throws — failures degrade to `{ available: false, sources: [] }` so
 * the library panel can render a disabled state.
 */
export async function listSources(): Promise<SourcesResponse> {
  try {
    const res = await fetch('/api/sources')
    if (!res.ok) return { available: false, sources: [] }
    return (await res.json()) as SourcesResponse
  } catch {
    return { available: false, sources: [] }
  }
}

/**
 * Parse an ingest response, throwing the server's error message on failure.
 * Shared by {@link uploadSource} and {@link ingestUrl}.
 */
async function ingestResult(res: Response): Promise<Source> {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error((data as { error?: string }).error || `Ingest failed (${res.status})`)
  return data as Source
}

/**
 * Upload a PDF into the library. Synchronous on the server — a big book takes
 * a while as it chunks + embeds, so callers should show a busy state.
 *
 * @param file  The PDF file.
 * @param title Optional display title (defaults to the filename server-side).
 * @throws With the server's error message when ingestion fails.
 */
export async function uploadSource(file: File, title?: string): Promise<Source> {
  const form = new FormData()
  form.append('file', file)
  if (title) form.append('title', title)
  return ingestResult(await fetch('/api/sources', { method: 'POST', body: form }))
}

/**
 * Ingest a web page (or a PDF link) by URL into the library.
 *
 * @param url   The page or PDF URL.
 * @param title Optional display title (defaults to the page title server-side).
 * @throws With the server's error message when ingestion fails.
 */
export async function ingestUrl(url: string, title?: string): Promise<Source> {
  return ingestResult(
    await fetch('/api/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, title }),
    }),
  )
}

/**
 * Remove a source and its chunks/vectors from the library.
 *
 * Never throws — returns false on any failure.
 */
export async function deleteSource(id: string): Promise<boolean> {
  try {
    const res = await fetch(`/api/sources/${encodeURIComponent(id)}`, { method: 'DELETE' })
    if (!res.ok) return false
    return ((await res.json()) as { deleted: boolean }).deleted
  } catch {
    return false
  }
}
