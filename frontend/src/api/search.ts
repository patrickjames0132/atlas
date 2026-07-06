/**
 * Seed search: find a paper to drop into the graph — live across Semantic
 * Scholar, or instantly from the local snapshot cache — with optional
 * date / field-of-study filters on the live search.
 */

import type { GraphNode } from './graph'

/**
 * The `/api/search` response: the echoed query plus its hits. Hits are full
 * graph-node shapes (the same type a graph neighbor has) — when the query
 * named a known paper, LLM-recalled + S2-verified matches lead the list.
 */
export interface LiveSearchResponse {
  q: string
  count: number
  papers: GraphNode[]
}

/**
 * Optional filters on the seed search. All fields are optional — an empty
 * filter set means "search everything", and filters never apply to an
 * explicit arXiv id/URL lookup.
 */
export interface SearchFilters {
  /** Earliest publication year (inclusive), or null for no floor. */
  yearFrom: number | null
  /** Latest publication year (inclusive), or null for no ceiling. */
  yearTo: number | null
  /** S2 fields of study to restrict to (any-of); empty = all fields. */
  fields: string[]
}

/** The no-op filter set (everything passes). */
export const EMPTY_FILTERS: SearchFilters = { yearFrom: null, yearTo: null, fields: [] }

/** Append a filter set to a query string (omitting inactive filters). */
function applyFilters(params: URLSearchParams, filters?: SearchFilters): void {
  if (!filters) return
  if (filters.yearFrom != null) params.set('year_from', String(filters.yearFrom))
  if (filters.yearTo != null) params.set('year_to', String(filters.yearTo))
  if (filters.fields.length) params.set('fields', filters.fields.join(','))
}

/**
 * Relevance search across Semantic Scholar to find a seed paper.
 *
 * Accepts keywords, a title, an author, or an arXiv id/URL — the backend
 * resolves ids/URLs directly to that exact paper (ignoring filters), and
 * expands free-text queries through the query analyst before the lexical
 * search runs.
 *
 * @param q       The search query.
 * @param limit   Maximum hits to return (default 25).
 * @param filters Optional date/field filters (see {@link SearchFilters}).
 * @throws When the request fails — seed search has no graceful fallback; the
 *         caller surfaces the error in the search UI.
 */
export async function searchLive(
  q: string,
  limit = 25,
  filters?: SearchFilters,
): Promise<LiveSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) })
  applyFilters(params, filters)
  const res = await fetch(`/api/search?${params.toString()}`)
  if (!res.ok) throw new Error(`Search failed (${res.status})`)
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
 * this must never block the live search running alongside it. The year
 * filter applies; the field filter doesn't (cached nodes are matched purely
 * on text).
 *
 * @param q       The search query.
 * @param limit   Maximum hits to return (default 10).
 * @param filters Optional filters — only the year window applies locally.
 */
export async function searchLocal(
  q: string,
  limit = 10,
  filters?: SearchFilters,
): Promise<LocalHit[]> {
  try {
    const params = new URLSearchParams({ q, limit: String(limit) })
    applyFilters(params, filters)
    params.delete('fields') // not supported locally
    const res = await fetch(`/api/local_search?${params.toString()}`)
    if (!res.ok) return []
    const data = await res.json()
    return (data.papers as LocalHit[]) ?? []
  } catch {
    return []
  }
}

/**
 * Fetch S2's fields of study (`/api/taxonomy/s2`) for the search filter's
 * field picker — ~20 coarse subjects like "Computer Science".
 *
 * Never throws — failures degrade to an empty list, which simply renders the
 * picker without options. (The backend also serves the ~155 arXiv categories
 * at `/api/taxonomy/arxiv`; no client function exists yet because nothing
 * consumes them until the detail-panel category-tags feature lands.)
 */
export async function getFields(): Promise<string[]> {
  try {
    const res = await fetch('/api/taxonomy/s2')
    if (!res.ok) return []
    return ((await res.json()) as { fields: string[] }).fields ?? []
  } catch {
    return []
  }
}
