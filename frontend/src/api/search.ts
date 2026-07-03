/**
 * Seed search: find a paper to drop into the graph, either fresh off arXiv or
 * instantly from the local snapshot cache.
 */

/** A seed-search hit from arXiv — pick one to drop into the graph. */
export interface ArxivHit {
  arxiv_id: string
  title: string
  authors: string
  abstract?: string
  categories?: string
  url?: string
}

/** The `/api/arxiv_search` response: the echoed query plus its hits. */
export interface ArxivSearchResponse {
  q: string
  count: number
  papers: ArxivHit[]
}

/**
 * Relevance search across arXiv to find a seed paper.
 *
 * Accepts keywords, a title, an author, or an arXiv id/URL — the backend
 * detects ids/URLs and resolves them directly.
 *
 * @param q     The search query.
 * @param limit Maximum hits to return (default 25).
 * @throws When the request fails — seed search has no graceful fallback; the
 *         caller surfaces the error in the search UI.
 */
export async function searchArxiv(
  q: string,
  limit = 25,
): Promise<ArxivSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) })
  const res = await fetch(`/api/arxiv_search?${params.toString()}`)
  if (!res.ok) throw new Error(`arXiv search failed (${res.status})`)
  return res.json()
}

/**
 * A paper found in the local snapshot cache — instant, and available even
 * when the live APIs are rate-limiting us.
 */
export interface LocalHit {
  /** Semantic Scholar paperId (always usable as a graph seed). */
  id: string
  arxiv_id: string | null
  title: string
  authors: string | null
  year: number | null
  citation_count: number | null
  url?: string | null
  /** A fresh graph snapshot exists — explores without hitting S2. */
  has_graph: boolean
}

/**
 * Instant search over papers already seen on previous graphs.
 *
 * Failures degrade to "no local hits" (an empty array) rather than throwing —
 * this must never block the live arXiv search running alongside it.
 *
 * @param q     The search query.
 * @param limit Maximum hits to return (default 10).
 */
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
