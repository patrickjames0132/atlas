// Typed client for the arXiv Digest backend API.

export interface Paper {
  arxiv_id: string
  title: string
  authors: string
  categories: string
  abstract: string
  url: string
  summary: string | null
  digest_date: string
}

export interface PapersResponse {
  date: string | null
  count: number
  papers: Paper[]
  dates: string[]
  followed_categories: string[]
}

export interface RefreshResult {
  ok: boolean
  error?: string
  emails_found?: number
  papers_parsed?: number
  papers_new?: number
  papers_summarized?: number
  digest_date?: string
}

export async function fetchPapers(date?: string): Promise<PapersResponse> {
  const qs = date ? `?date=${encodeURIComponent(date)}` : ''
  const res = await fetch(`/api/papers${qs}`)
  if (!res.ok) throw new Error(`Failed to load papers (${res.status})`)
  return res.json()
}

// Refresh only requeries arXiv for new papers; summaries are per-row on demand.
export async function refresh(summarize = false): Promise<RefreshResult> {
  const res = await fetch('/api/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ summarize }),
  })
  return res.json()
}

// Generate (or fetch the cached) summary for a single paper.
export async function fetchSummary(arxivId: string): Promise<string> {
  const res = await fetch(
    `/api/papers/${encodeURIComponent(arxivId)}/summary`,
    { method: 'POST' },
  )
  const data = await res.json()
  if (!res.ok || !data.ok) {
    throw new Error(data.error || `Failed to summarize (${res.status})`)
  }
  return data.summary as string
}

// Returns the URL that downloads a NotebookLM-ready Markdown digest.
export function notebookLmExportUrl(date?: string): string {
  const qs = date ? `?date=${encodeURIComponent(date)}` : ''
  return `/api/export/notebooklm${qs}`
}
