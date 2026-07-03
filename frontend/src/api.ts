// Typed client for the arXiv Atlas backend API.

// A seed-search hit from arXiv — pick one to drop into the graph.
export interface ArxivHit {
  arxiv_id: string
  title: string
  authors: string
  abstract?: string
  categories?: string
  url?: string
}

export interface ArxivSearchResponse {
  q: string
  count: number
  papers: ArxivHit[]
}

// Relevance search across arXiv to find a seed paper; accepts keywords, a title,
// an author, or an arXiv id/URL.
export async function searchArxiv(
  q: string,
  limit = 25,
): Promise<ArxivSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) })
  const res = await fetch(`/api/arxiv_search?${params.toString()}`)
  if (!res.ok) throw new Error(`arXiv search failed (${res.status})`)
  return res.json()
}

// A paper found in the local snapshot cache — instant, and available even when
// the live APIs are rate-limiting us.
export interface LocalHit {
  id: string // Semantic Scholar paperId (always usable as a graph seed)
  arxiv_id: string | null
  title: string
  authors: string | null
  year: number | null
  citation_count: number | null
  url?: string | null
  has_graph: boolean // a fresh graph snapshot exists — explores without hitting S2
}

// Instant search over papers already seen on previous graphs. Failures degrade
// to "no local hits" — this must never block the live search.
export async function searchLocal(q: string, limit = 10): Promise<LocalHit[]> {
  try {
    const params = new URLSearchParams({ q, limit: String(limit) })
    const res = await fetch(`/api/local_search?${params.toString()}`)
    if (!res.ok) return []
    const data = await res.json()
    return (data.papers as LocalHit[]) ?? []
  } catch {
    return []
  }
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
  rels: string[] // 'seed' | 'reference' | 'citation' | 'similar' | 'search'
  is_seed: boolean
  discovered?: boolean // added mid-conversation by the agent's expand_node tool
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

// A backward-in-time hop the history lecture took before narrating (Phase 3e):
// how many foundational ancestors it pulled in and the oldest year it reached.
export interface LectureTrace {
  hop: number
  found: number
  oldest: number | null
  error?: boolean // the hop hit an S2 error / rate limit rather than empty results
}

export interface LectureHandlers {
  onBeat: (beat: Beat) => void
  onTrace?: (t: LectureTrace) => void // history-mode backward hops
  onNodes?: (d: Discovery) => void // ancestors pulled in, to merge into the graph
  onDone?: () => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

// Stream a lecture over the visible graph. Beats arrive one at a time. In history
// mode, trace + nodes events (the backward walk to the field's roots) precede them.
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
    else if (event === 'trace') h.onTrace?.(data as LectureTrace)
    else if (event === 'nodes') h.onNodes?.(data as Discovery)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { error: string }).error)
  })
}

// A step the agent took — reading a paper, expanding the graph to one not yet
// shown, or searching S2 for off-graph papers. Surfaced live as the agent works.
export interface TraceEvent {
  action: 'read' | 'expand' | 'search' | 'search_sources'
  ok: boolean
  title?: string | null
  index?: number
  detail?: string // 'summary' | 'full' — read_paper
  relation?: string // 'references' | 'citations' | 'similar' — expand_node
  found?: number // new papers discovered / passages found
  query?: string // free-text query — search_papers / search_sources
  year_from?: number | null // year filter — search_papers
  year_to?: number | null
}

// New papers (+ the edges connecting them) the agent pulled in via expand_node,
// to be merged into the live graph.
export interface Discovery {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface AskHandlers {
  onToken: (text: string) => void
  onCited: (nodeIds: string[]) => void
  onTrace?: (t: TraceEvent) => void
  onNodes?: (d: Discovery) => void
  onDiscard?: () => void // drop streamed preamble that preceded a tool call
  onDone?: () => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

// Stream a grounded answer: agent trace steps, prose tokens, then the nodes it
// drew from. (Non-agentic backends just emit tokens + cited.)
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
    else if (event === 'trace') h.onTrace?.(data as TraceEvent)
    else if (event === 'nodes') h.onNodes?.(data as Discovery)
    else if (event === 'discard') h.onDiscard?.()
    else if (event === 'cited') h.onCited((data as { node_ids: string[] }).node_ids)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { error: string }).error)
  })
}

// Offline library chat (Phase 3d): the one trace it emits — which passages the
// retrieval pulled, and from which sources — shown above the grounded answer.
export interface RetrieveEvent {
  found: number
  sources: string[]
}

export interface AskSourcesHandlers {
  onToken: (text: string) => void
  onRetrieve?: (r: RetrieveEvent) => void
  onDone?: () => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

// Stream an answer grounded purely in the user's local library — no graph. A
// single retrieve event, then prose tokens. Pass source_id to scope to one source.
export async function streamAskSources(
  body: { question: string; session_id: string; source_id?: string },
  h: AskSourcesHandlers,
): Promise<void> {
  const res = await fetch('/api/ask_sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: h.signal,
  })
  await readSSE(res, (event, data) => {
    if (event === 'token') h.onToken((data as { text: string }).text)
    else if (event === 'trace') h.onRetrieve?.(data as RetrieveEvent)
    else if (event === 'done') h.onDone?.()
    else if (event === 'error') h.onError?.((data as { error: string }).error)
  })
}

// --- Bring-your-own sources: the user's local semantic library (Phase 3d) ----

export interface Source {
  id: string
  title: string
  kind: 'pdf' | 'url'
  origin: string | null
  pages: number | null
  n_chunks: number
  created_at: string
}

export interface SourcesResponse {
  available: boolean // local embeddings + sqlite-vec loaded
  sources: Source[]
}

export async function listSources(): Promise<SourcesResponse> {
  try {
    const res = await fetch('/api/sources')
    if (!res.ok) return { available: false, sources: [] }
    return (await res.json()) as SourcesResponse
  } catch {
    return { available: false, sources: [] }
  }
}

async function ingestResult(res: Response): Promise<Source> {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error((data as { error?: string }).error || `Ingest failed (${res.status})`)
  return data as Source
}

export async function uploadSource(file: File, title?: string): Promise<Source> {
  const form = new FormData()
  form.append('file', file)
  if (title) form.append('title', title)
  return ingestResult(await fetch('/api/sources', { method: 'POST', body: form }))
}

export async function ingestUrl(url: string, title?: string): Promise<Source> {
  return ingestResult(
    await fetch('/api/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, title }),
    }),
  )
}

export async function deleteSource(id: string): Promise<boolean> {
  try {
    const res = await fetch(`/api/sources/${encodeURIComponent(id)}`, { method: 'DELETE' })
    if (!res.ok) return false
    return ((await res.json()) as { deleted: boolean }).deleted
  } catch {
    return false
  }
}
