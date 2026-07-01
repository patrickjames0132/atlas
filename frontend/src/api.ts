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
  start: string | null
  end: string | null
  count: number
  papers: Paper[]
  dates: string[]
  followed_categories: string[]
}

export interface RefreshResult {
  ok: boolean
  error?: string
  papers_fetched?: number
  papers_new?: number
  papers_summarized?: number
  start_date?: string
  end_date?: string
}

// Build a `?start=&end=` query string, omitting empty bounds.
function rangeQuery(start?: string, end?: string): string {
  const params = new URLSearchParams()
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export async function fetchPapers(
  start?: string,
  end?: string,
): Promise<PapersResponse> {
  const res = await fetch(`/api/papers${rangeQuery(start, end)}`)
  if (!res.ok) throw new Error(`Failed to load papers (${res.status})`)
  return res.json()
}

// Pull papers submitted in [start, end] (default: today) from arXiv. Summaries
// are generated per-row on demand, so this only fetches & stores the papers.
export async function refresh(
  start?: string,
  end?: string,
  summarize = false,
): Promise<RefreshResult> {
  const res = await fetch('/api/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start, end, summarize }),
  })
  return res.json()
}

export interface SearchResponse {
  q: string
  start: string | null
  end: string | null
  mode: 'hybrid' | 'lexical'
  count: number
  papers: Paper[]
}

// Hybrid (keyword + semantic) search over stored papers, ranked by fused
// relevance. When start/end are given the search is scoped to that date range.
// `mode` reports whether the semantic half ran ("hybrid") or it fell back to
// keyword-only ("lexical").
export async function searchPapers(
  q: string,
  start?: string,
  end?: string,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q })
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  const res = await fetch(`/api/search?${params.toString()}`)
  if (!res.ok) throw new Error(`Search failed (${res.status})`)
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

export interface Category {
  code: string
  name: string
}

export interface CategoryGroup {
  group: string
  categories: Category[]
}

export interface CategoriesResponse {
  groups: CategoryGroup[]
  followed: string[]
}

// The full arXiv taxonomy plus the categories the user currently follows.
export async function fetchCategories(): Promise<CategoriesResponse> {
  const res = await fetch('/api/categories')
  if (!res.ok) throw new Error(`Failed to load categories (${res.status})`)
  return res.json()
}

// Replace the followed-category set; returns the saved (cleaned) list.
export async function saveCategories(followed: string[]): Promise<string[]> {
  const res = await fetch('/api/categories', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ followed }),
  })
  const data = await res.json()
  if (!res.ok || !data.ok) {
    throw new Error(data.error || `Failed to save categories (${res.status})`)
  }
  return data.followed as string[]
}

// Returns the URL that downloads a NotebookLM-ready Markdown digest.
export function notebookLmExportUrl(start?: string, end?: string): string {
  return `/api/export/notebooklm${rangeQuery(start, end)}`
}
