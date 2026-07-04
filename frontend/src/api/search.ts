/**
 * Seed search: find a paper to drop into the graph, either fresh off arXiv or
 * instantly from the local snapshot cache — with optional date / category
 * filters on the live search.
 */

/** A seed-search hit from arXiv — pick one to drop into the graph. */
export interface ArxivHit {
  arxiv_id: string
  title: string
  authors: string
  abstract?: string
  /** Space-separated arXiv category codes (e.g. "cs.LG cs.CV"). */
  categories?: string
  url?: string
  /** The paper's submission day (GMT) as "YYYY-MM-DD". */
  published?: string
}

/** The `/api/arxiv_search` response: the echoed query plus its hits. */
export interface ArxivSearchResponse {
  q: string
  count: number
  papers: ArxivHit[]
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
  /** arXiv category codes to restrict to (any-of); empty = all categories. */
  categories: string[]
}

/** The no-op filter set (everything passes). */
export const EMPTY_FILTERS: SearchFilters = { yearFrom: null, yearTo: null, categories: [] }

/** Append a filter set to a query string (omitting inactive filters). */
function applyFilters(params: URLSearchParams, filters?: SearchFilters): void {
  if (!filters) return
  if (filters.yearFrom != null) params.set('year_from', String(filters.yearFrom))
  if (filters.yearTo != null) params.set('year_to', String(filters.yearTo))
  if (filters.categories.length) params.set('categories', filters.categories.join(','))
}

/**
 * Relevance search across arXiv to find a seed paper.
 *
 * Accepts keywords, a title, an author, or an arXiv id/URL — the backend
 * detects ids/URLs and resolves them directly (ignoring filters).
 *
 * @param q       The search query.
 * @param limit   Maximum hits to return (default 25).
 * @param filters Optional date/category filters (see {@link SearchFilters}).
 * @throws When the request fails — seed search has no graceful fallback; the
 *         caller surfaces the error in the search UI.
 */
export async function searchArxiv(
  q: string,
  limit = 25,
  filters?: SearchFilters,
): Promise<ArxivSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) })
  applyFilters(params, filters)
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
 * this must never block the live arXiv search running alongside it. The year
 * filter applies; the category filter doesn't (S2 nodes don't carry arXiv
 * categories).
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
    params.delete('categories') // not supported locally
    const res = await fetch(`/api/local_search?${params.toString()}`)
    if (!res.ok) return []
    const data = await res.json()
    return (data.papers as LocalHit[]) ?? []
  } catch {
    return []
  }
}

/** One category in the arXiv taxonomy (e.g. cs.LG / "Machine Learning"). */
export interface TaxonomyCategory {
  code: string
  name: string
}

/** A top-level taxonomy area (e.g. "Computer Science") and its categories. */
export interface TaxonomyGroup {
  group: string
  categories: TaxonomyCategory[]
}

/**
 * Fetch the arXiv category taxonomy for the search filter's category picker.
 *
 * Never throws — failures degrade to an empty list, which simply renders the
 * picker without options.
 */
export async function getTaxonomy(): Promise<TaxonomyGroup[]> {
  try {
    const res = await fetch('/api/taxonomy')
    if (!res.ok) return []
    return ((await res.json()) as { groups: TaxonomyGroup[] }).groups ?? []
  } catch {
    return []
  }
}
