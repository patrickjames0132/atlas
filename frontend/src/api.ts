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
  // date -> categories already fetched from arXiv for that day.
  coverage: Record<string, string[]>
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

// A live arXiv-search result: a normal paper plus whether it's already stored.
export interface ArxivHit extends Paper {
  in_library: boolean
}

export interface ArxivSearchResponse {
  q: string
  count: number
  papers: ArxivHit[]
}

// Live relevance search across ALL of arXiv (not just the local library). Ignores
// the date range; accepts keywords, a title, an author, or an arXiv id/URL.
export async function searchArxiv(
  q: string,
  limit = 25,
): Promise<ArxivSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) })
  const res = await fetch(`/api/arxiv_search?${params.toString()}`)
  if (!res.ok) throw new Error(`arXiv search failed (${res.status})`)
  return res.json()
}

// Add a live arXiv-search result to the library (fetch -> store -> embed).
export async function addArxivPaper(arxivId: string): Promise<void> {
  const res = await fetch('/api/arxiv_search/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arxiv_id: arxivId }),
  })
  const data = await res.json()
  if (!res.ok || !data.ok) {
    throw new Error(data.error || `Failed to add paper (${res.status})`)
  }
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

// --- arXiv Atlas: the paper neighborhood graph -------------------------------

export type EdgeType = 'reference' | 'citation' | 'similar'

export interface GraphNode {
  id: string // Semantic Scholar paperId (stable graph key)
  arxiv_id: string | null
  title: string
  abstract?: string | null
  tldr?: string | null
  year: number | null
  month?: number | null // 1–12 from S2 publicationDate; for timeline placement
  pub_date?: string | null // full "YYYY-MM-DD" from S2, when known
  citation_count: number | null
  authors?: string | null
  url: string | null
  rels: string[] // 'seed' | 'reference' | 'citation' | 'similar'
  is_seed: boolean
}

export interface GraphEdge {
  source: string
  target: string
  type: EdgeType
  influential?: boolean
}

export interface GraphResponse {
  seed: { arxiv_id: string; id: string; title: string }
  nodes: GraphNode[]
  edges: GraphEdge[]
  counts: {
    references: number
    citations: number
    similar: number
    nodes: number
  }
}

// The neighborhood graph for a seed paper (references + citations + similar).
// `seed` is an arXiv id or a pasted abs/pdf URL; `refresh` bypasses the cache.
export async function fetchGraph(
  seed: string,
  refresh = false,
): Promise<GraphResponse> {
  const params = new URLSearchParams({ seed })
  if (refresh) params.set('refresh', '1')
  const res = await fetch(`/api/graph?${params.toString()}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.error || `Failed to load graph (${res.status})`)
  }
  return res.json()
}

// Full details (abstract, tldr, authors) for one paper — hydrates a node panel.
export async function fetchPaperDetail(arxivId: string): Promise<GraphNode> {
  const res = await fetch(`/api/paper/${encodeURIComponent(arxivId)}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.error || `Failed to load paper (${res.status})`)
  }
  return res.json()
}

// A figure pulled from the paper (via ar5iv): a proxied image URL + the paper's
// own caption.
export interface Figure {
  image: string
  caption: string
}

export interface FiguresResponse {
  available: boolean
  figures: Figure[]
}

// The paper's figures + captions for the detail panel. `available` is false when
// ar5iv has no render for the paper (older / PDF-only submissions).
export async function fetchFigures(arxivId: string): Promise<FiguresResponse> {
  const res = await fetch(`/api/paper/${encodeURIComponent(arxivId)}/figures`)
  if (!res.ok) return { available: false, figures: [] }
  return res.json()
}

// --- arXiv Atlas: the AI teacher (streaming lecture + Q&A) --------------------

// One beat of a lecture: a paragraph of narration bound to the graph nodes it's
// about, so they light up in sync as the beat is revealed.
export interface Beat {
  heading: string
  text: string
  node_ids: string[]
}

// A trimmed node the teacher needs — the visible graph is its grounding scope.
export interface TeacherNode {
  id: string
  title: string
  year: number | null
  citation_count?: number | null
  authors?: string | null
  tldr?: string | null
  abstract?: string | null
  rels: string[]
}

export type LectureMode = 'history' | 'intuition' | 'bridge'

// Read a `text/event-stream` POST response, dispatching each frame to `onEvent`
// as (eventName, parsedData). Shared by the lecture + Q&A streamers.
async function readSSE(
  res: Response,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}))
    throw new Error((data as { error?: string }).error || `Request failed (${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let sep: number
    // Frames are separated by a blank line.
    while ((sep = buf.indexOf('\n\n')) !== -1) {
      const frame = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      let event = 'message'
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      try {
        onEvent(event, JSON.parse(data))
      } catch {
        /* ignore malformed frame */
      }
    }
  }
}

export interface LectureHandlers {
  onBeat: (beat: Beat) => void
  onDone?: () => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

// Stream a lecture over the visible graph. Beats arrive one at a time.
export async function streamLecture(
  body: { seed: { title: string; id?: string }; nodes: TeacherNode[]; mode: LectureMode; target?: { title: string } },
  h: LectureHandlers,
): Promise<void> {
  const res = await fetch('/api/lecture', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: h.signal,
  })
  await readSSE(res, (event, data) => {
    if (event === 'beat') h.onBeat(data as Beat)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { error: string }).error)
  })
}

export interface AskHandlers {
  onToken: (text: string) => void
  onCited: (nodeIds: string[]) => void
  onDone?: () => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

// Stream a grounded answer: prose tokens, then the nodes it cited.
export async function streamAsk(
  body: { question: string; session_id: string; seed: { title: string; id?: string }; nodes: TeacherNode[] },
  h: AskHandlers,
): Promise<void> {
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: h.signal,
  })
  await readSSE(res, (event, data) => {
    if (event === 'token') h.onToken((data as { text: string }).text)
    else if (event === 'cited') h.onCited((data as { node_ids: string[] }).node_ids)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { error: string }).error)
  })
}

// Returns the URL that downloads a NotebookLM-ready Markdown digest. When `q` is
// given, the digest contains only that search's results (else the whole range).
export function notebookLmExportUrl(
  start?: string,
  end?: string,
  q?: string,
): string {
  const params = new URLSearchParams()
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  if (q && q.trim()) params.set('q', q.trim())
  const qs = params.toString()
  return `/api/export/notebooklm${qs ? `?${qs}` : ''}`
}
