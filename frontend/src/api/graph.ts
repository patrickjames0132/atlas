/**
 * The paper neighborhood graph — nodes, edges, single-paper detail hydration,
 * and a paper's figures.
 */

/** How two papers on the graph relate. */
export type EdgeType = 'reference' | 'citation' | 'similar'

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
  /** Roles relative to the seed: 'seed' | 'reference' | 'citation' | 'similar' | 'search'. */
  rels: string[]
  is_seed: boolean
  /** Added mid-conversation by the researcher's expand_node / search_papers tools. */
  discovered?: boolean
  /**
   * The [n] index the researcher knows the paper by (discovered papers only;
   * null when the lecture backfill found it, before numbering exists).
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
    nodes: number
  }
}

/**
 * The neighborhood graph for a seed paper (references + citations + similar).
 *
 * @param seed    An arXiv id, a pasted abs/pdf URL, or a raw S2 paperId
 *                (re-seeding works from any node, arXiv or not).
 * @param refresh Bypass the server's day-cached snapshot and rebuild from S2.
 * @throws With the server's error message (e.g. "No paper found…", S2
 *         unavailable) when the graph can't be built.
 */
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

/**
 * Full details (abstract, tldr, authors) for one paper — used to hydrate a
 * node's detail panel on click, since graph nodes arrive summary-light.
 *
 * @param paperRef The paper's arXiv id, a pasted abs/pdf URL, or a raw S2
 *                 paperId (papers that exist on S2 but not arXiv hydrate by
 *                 paperId).
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
 */
export async function fetchCodeLinks(arxivId: string): Promise<CodeLinksResponse> {
  const res = await fetch(`/api/paper/${encodeURIComponent(arxivId)}/code`)
  if (!res.ok) return EMPTY_CODE_LINKS
  return res.json()
}
