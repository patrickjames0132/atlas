/**
 * The paper neighborhood graph — nodes, edges, single-paper detail hydration,
 * and a paper's figures.
 */

import { readSSE } from './sse'

/**
 * The academic-data backend a graph is built from. Chosen per graph in the
 * header dropdown and sent on every graph request; the server defaults to
 * `config.graph.default_provider` when it's omitted. A graph is built from ONE
 * provider end-to-end — no cross-source hybrid.
 */
export type Provider = 's2' | 'openalex'

/** Human-readable provider names for the dropdown / UI. */
export const PROVIDER_LABEL: Record<Provider, string> = {
  s2: 'Semantic Scholar',
  openalex: 'OpenAlex',
}

/** How two papers on the graph relate. */
export type EdgeType = 'reference' | 'citation' | 'similar' | 'latest'

/**
 * One paper on the graph. Shape mirrors the backend's `services.graph.Node`
 * (the normalized Semantic Scholar node plus the graph-role flags), and is
 * also the shape of a live-search hit and a discovered paper — one paper
 * type everywhere.
 */
export interface GraphNode {
  /** Semantic Scholar paperId (stable graph key). */
  id: string
  arxiv_id: string | null
  title: string
  abstract?: string | null
  tldr?: string | null
  year: number | null
  /** 1–12 from S2 publicationDate; for timeline placement between year lines. */
  month?: number | null
  /** Full "YYYY-MM-DD" from S2, when known. */
  pub_date?: string | null
  citation_count: number | null
  authors?: string | null
  url: string | null
  /**
   * Semantic Scholar's own field-of-study categories (e.g. "Computer
   * Science", "Mathematics"), shown as a tag layer beside the paper's arXiv
   * categories. Empty for graph neighbors until the detail panel hydrates
   * them on open; a restored pre-v2.6 session may omit it entirely.
   */
  fields_of_study?: string[]
  /** Roles relative to the seed: 'seed' | 'reference' | 'citation' | 'latest' | 'similar' | 'search'. */
  rels: string[]
  is_seed: boolean
  /** Added mid-conversation by the researcher's expand_node / search_papers tools. */
  discovered?: boolean
  /**
   * The [n] index the researcher knows the paper by (discovered papers only;
   * null on discoveries restored from old saves, from before numbering).
   */
  idx?: number | null
}

/** A directed edge between two papers (source/target are node ids). */
export interface GraphEdge {
  source: string
  target: string
  type: EdgeType
  /**
   * S2 flagged this as an influential citation (drawn heavier). Explicitly
   * null on 'similar' edges — they aren't citations, so the flag doesn't
   * apply.
   */
  influential?: boolean | null
  /**
   * 0-based position within this edge's relation, in the relation's own order
   * (references/citations by citation count, latest by recency, similar by S2
   * similarity). The frontend no longer trims by rank (the per-relation count
   * sliders were retired in favor of the citation-count threshold slider), but
   * the backend still ranks the shipped pool, so the field is preserved for
   * snapshots and any future rank-aware view. Absent on old snapshots.
   */
  rank?: number
}

/** The `/api/graph` response: the resolved seed, its neighborhood, and counts. */
export interface GraphResponse {
  seed: { arxiv_id: string | null; id: string; title: string }
  nodes: GraphNode[]
  edges: GraphEdge[]
  counts: {
    references: number
    citations: number
    similar: number
    latest: number
    nodes: number
  }
}

/**
 * The neighborhood graph for a seed paper (references + citations).
 *
 * @param seed     An arXiv id, a pasted abs/pdf URL, or a raw provider node id
 *                 (re-seeding works from any node, arXiv or not).
 * @param provider Which backend to build from ('s2' / 'openalex').
 * @param refresh  Bypass the server's day-cached snapshot and rebuild.
 * @returns The seed's whole neighborhood graph (nodes, edges, counts).
 * @throws With the server's error message (e.g. "No paper found…", provider
 *         unavailable) when the graph can't be built.
 */
export async function fetchGraph(
  seed: string,
  provider: Provider,
  refresh = false,
): Promise<GraphResponse> {
  const params = new URLSearchParams({ seed, provider })
  if (refresh) params.set('refresh', '1')
  const res = await fetch(`/api/graph?${params.toString()}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.error || `Failed to load graph (${res.status})`)
  }
  return res.json()
}

/** One coarse stage of an in-flight graph build: which step, of how many. */
export interface BuildProgress {
  done: number
  total: number
  /** Human-readable stage label, e.g. "Fetching citations…". */
  label: string
}

/**
 * The neighborhood graph for a seed, via the SSE build endpoint — identical
 * result to {@link fetchGraph}, but reporting coarse build progress as it goes
 * so the "Building graph…" overlay can show a real bar. A cached snapshot
 * emits no `progress` frames (the server returns it before the first stage),
 * so `onProgress` simply never fires and the graph resolves at once.
 *
 * @param seed       An arXiv id, a pasted abs/pdf URL, or a raw provider node id.
 * @param provider   Which backend to build from ('s2' / 'openalex').
 * @param refresh    Bypass the server's day-cached snapshot and rebuild.
 * @param onProgress Called per build stage with `{done, total, label}`.
 * @returns The seed's whole neighborhood graph, same shape as {@link fetchGraph}.
 * @throws With the server's error message when the graph can't be built.
 */
export async function fetchGraphStream(
  seed: string,
  provider: Provider,
  refresh = false,
  onProgress?: (progress: BuildProgress) => void,
): Promise<GraphResponse> {
  const params = new URLSearchParams({ seed, provider })
  if (refresh) params.set('refresh', '1')
  const res = await fetch(`/api/graph/stream?${params.toString()}`)
  let graph: GraphResponse | null = null
  let message: string | null = null
  await readSSE(res, (event, data) => {
    if (event === 'progress') onProgress?.(data as BuildProgress)
    else if (event === 'done') graph = data as GraphResponse
    else if (event === 'error') message = (data as { message: string }).message
  })
  if (message) throw new Error(message)
  if (!graph) throw new Error('Graph build failed (stream ended early)')
  return graph
}

/**
 * Full details (abstract, tldr, authors) for one paper — used to hydrate a
 * node's detail panel on click, since graph nodes arrive summary-light.
 *
 * @param paperRef The paper's arXiv id, a pasted abs/pdf URL, or a raw S2
 *                 paperId (papers that exist on S2 but not arXiv hydrate by
 *                 paperId).
 * @returns The hydrated node (abstract, tldr, authors filled in).
 * @throws With the server's error message when the paper can't be fetched.
 */
export async function fetchPaperDetail(paperRef: string): Promise<GraphNode> {
  const res = await fetch(`/api/paper/${encodeURIComponent(paperRef)}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.error || `Failed to load paper (${res.status})`)
  }
  return res.json()
}

/**
 * A figure pulled from the paper (via ar5iv): a proxied image URL + the
 * paper's own caption.
 */
export interface Figure {
  image: string
  caption: string
}

/** The `/api/paper/<id>/figures` response. */
export interface FiguresResponse {
  /** False when ar5iv has no render for the paper (older / PDF-only submissions). */
  available: boolean
  figures: Figure[]
}

/**
 * The paper's figures + captions for the detail panel.
 *
 * Never throws — failures degrade to `{ available: false }` so a flaky ar5iv
 * can't break the panel.
 *
 * @param arxivId The paper's arXiv id.
 * @returns The figure list, or `{available: false}` when ar5iv has no render.
 */
export async function fetchFigures(arxivId: string): Promise<FiguresResponse> {
  const res = await fetch(`/api/paper/${encodeURIComponent(arxivId)}/figures`)
  if (!res.ok) return { available: false, figures: [] }
  return res.json()
}

/** A model/dataset/Space on Hugging Face linked to the paper. */
export interface CodeRepo {
  /** The HF repo id, e.g. `google/paligemma-3b-pt-224`. */
  id: string
  url: string
  likes: number
  /** Models & datasets only. */
  downloads?: number
  /** Models only, e.g. `text-generation`. */
  pipeline_tag?: string | null
  /** Spaces only. */
  emoji?: string | null
}

/** The `/api/paper/<id>/code` response (from Hugging Face Papers). */
export interface CodeLinksResponse {
  /** False when HF has never indexed the paper (or HF is unreachable). */
  available: boolean
  /** The HF paper page (lists everything, incl. community discussion). */
  paper_url: string | null
  upvotes: number
  /** The community-linked implementation repo, when someone has linked one. */
  github: { url: string; stars: number } | null
  models: CodeRepo[]
  datasets: CodeRepo[]
  spaces: CodeRepo[]
  /** Full linked-repo counts on HF (the lists above are samples). */
  totals: { models: number; datasets: number; spaces: number }
}

const EMPTY_CODE_LINKS: CodeLinksResponse = {
  available: false,
  paper_url: null,
  upvotes: 0,
  github: null,
  models: [],
  datasets: [],
  spaces: [],
  totals: { models: 0, datasets: 0, spaces: 0 },
}

/**
 * The paper's code & artifact links (Hugging Face Papers) for the detail panel.
 *
 * Never throws — failures degrade to `{ available: false }` so a flaky HF
 * can't break the panel.
 *
 * @param arxivId The paper's arXiv id.
 * @returns The linked repos/models/datasets, or `{available: false}`.
 */
export async function fetchCodeLinks(arxivId: string): Promise<CodeLinksResponse> {
  const res = await fetch(`/api/paper/${encodeURIComponent(arxivId)}/code`)
  if (!res.ok) return EMPTY_CODE_LINKS
  return res.json()
}

/** One of a paper's own arXiv category tags, e.g. `{code: "cs.LG", name: "Machine Learning"}`. */
export interface Category {
  code: string
  name: string
}

/** The `/api/paper/<id>/categories` response. */
export interface CategoriesResponse {
  /** False for a bad/withdrawn id — S2-only (non-arXiv) papers have none either. */
  available: boolean
  /** Primary category first, as arXiv itself orders them. */
  categories: Category[]
}

const EMPTY_CATEGORIES: CategoriesResponse = { available: false, categories: [] }

/**
 * The paper's own arXiv category tags for the detail panel.
 *
 * Never throws — failures degrade to `{ available: false }` so a flaky arXiv
 * export API can't break the panel.
 *
 * @param arxivId The paper's arXiv id.
 * @returns The category tags, or `{available: false}`.
 */
export async function fetchCategories(arxivId: string): Promise<CategoriesResponse> {
  const res = await fetch(`/api/paper/${encodeURIComponent(arxivId)}/categories`)
  if (!res.ok) return EMPTY_CATEGORIES
  return res.json()
}
