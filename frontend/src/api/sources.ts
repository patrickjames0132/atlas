/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Bring-your-own sources: the user's local semantic library.
 *
 * Sources are PDFs or web pages ingested server-side (chunked + embedded into
 * a sqlite-vec index) that the teacher can semantically search. Ingestion
 * streams SSE progress frames — embedding is where the time goes.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { readSSE } from './sse'

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
 *
 * @returns The source list, or the disabled shape on any failure.
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

/** Embedding progress for an in-flight ingestion: chunks done / total. */
export interface IngestProgress {
  done: number
  total: number
}

/**
 * Consume an ingestion's SSE stream: `progress` frames feed the callback,
 * `done` resolves with the stored record, `error` rejects with the server's
 * message (a SourceError's text verbatim — written for users).
 * Shared by {@link uploadSource} and {@link ingestUrl}.
 *
 * @param res        The ingestion endpoint's SSE response.
 * @param onProgress Called per embedding batch with `{done, total}` chunks.
 * @returns The stored source record once the stream completes.
 */
async function ingestResult(
  res: Response,
  onProgress?: (progress: IngestProgress) => void,
): Promise<Source> {
  let source: Source | null = null
  let message: string | null = null
  await readSSE(res, (event, data) => {
    if (event === 'progress') onProgress?.(data as IngestProgress)
    else if (event === 'done') source = data as Source
    else if (event === 'error') message = (data as { message: string }).message
  })
  if (message) throw new Error(message)
  if (!source) throw new Error('Ingest failed (stream ended early)')
  return source
}

/**
 * Upload a PDF into the library. A big book takes a while as it chunks +
 * embeds — the server streams embedding progress so callers can render a
 * real bar, not just a spinner.
 *
 * @param file       The PDF file.
 * @param title      Optional display title (defaults to the filename server-side).
 * @param onProgress Called per embedding batch with `{done, total}` chunks.
 * @returns The stored source record.
 * @throws With the server's error message when ingestion fails.
 */
export async function uploadSource(
  file: File,
  title?: string,
  onProgress?: (progress: IngestProgress) => void,
): Promise<Source> {
  const form = new FormData()
  form.append('file', file)
  if (title) form.append('title', title)
  return ingestResult(await fetch('/api/sources', { method: 'POST', body: form }), onProgress)
}

/**
 * Ingest a web page (or a PDF link) by URL into the library.
 *
 * @param url        The page or PDF URL.
 * @param title      Optional display title (defaults to the page title server-side).
 * @param onProgress Called per embedding batch with `{done, total}` chunks.
 * @returns The stored source record.
 * @throws With the server's error message when ingestion fails.
 */
export async function ingestUrl(
  url: string,
  title?: string,
  onProgress?: (progress: IngestProgress) => void,
): Promise<Source> {
  return ingestResult(
    await fetch('/api/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, title }),
    }),
    onProgress,
  )
}

/**
 * Remove a source and its chunks/vectors from the library.
 *
 * Never throws — returns false on any failure.
 *
 * @param id The source's id.
 * @returns True when the source existed and is now gone.
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
