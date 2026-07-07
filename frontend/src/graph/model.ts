/**
 * The explorer's view-model types and pure helpers: how API nodes become live
 * simulation nodes, and the small derivations (radius, primary relation,
 * date formatting) shared by the canvas and the DOM panels.
 */

import type { GraphEdge, GraphNode, GraphResponse } from '../api'
import { REL_TYPES } from './theme'

/**
 * A pasted arXiv id or abs/pdf URL — jump straight to a graph instead of a
 * keyword search. Mirrors the backend's tolerance.
 */
export const ID_RE =
  /^(?:https?:\/\/arxiv\.org\/(?:abs|pdf)\/)?(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?\/\d{7}(?:v\d+)?)$/i

/**
 * A live simulation node: a GraphNode that react-force-graph has (or will)
 * decorate with position (`x`/`y`) and optional pin coordinates (`fx`/`fy`).
 */
export type VNode = GraphNode & { x?: number; y?: number; fx?: number; fy?: number }

/**
 * A live simulation link. RFG mutates `source`/`target` from ids into node
 * object references, so `_s`/`_t` preserve the raw endpoint ids for filtering
 * and persistence.
 */
export type VLink = GraphEdge & { _s: string; _t: string }

/**
 * The stable per-graph dataset behind the filtered view: the mutable node and
 * link objects (which MUST keep identity across filter changes so sim
 * positions and pins survive), plus the year range and per-relation counts.
 */
export type Base = {
  nodes: VNode[]
  links: VLink[]
  minYear: number
  maxYear: number
  counts: Record<string, number>
}

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

/**
 * Human-readable publication date: "Jun 12, 2017" from a "YYYY-MM-DD" string,
 * gracefully degrading to "Jun 2017" / the year / "—" as data thins out.
 *
 * Parsed by hand (not `new Date`) to avoid timezone off-by-one on date-only
 * strings.
 */
export function formatPubDate(pubDate?: string | null, year?: number | null): string {
  if (pubDate) {
    const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(pubDate)
    if (m) {
      const mon = MONTHS[Number(m[2]) - 1]
      if (mon && m[3]) return `${mon} ${Number(m[3])}, ${m[1]}`
      if (mon) return `${mon} ${m[1]}`
      return m[1]
    }
  }
  return year != null ? String(year) : '—'
}

/**
 * The single relation that decides a node's color: seed wins, then the first
 * graph relation in priority order, then topic-search hits get their own
 * color, falling back to 'similar'.
 */
export function primaryRel(node: GraphNode): string {
  if (node.is_seed) return 'seed'
  for (const rel of REL_TYPES) if (node.rels.includes(rel)) return rel
  // Ungrounded topic-search hits (no graph relation) get their own color.
  if (node.rels.includes('search')) return 'search'
  return 'similar'
}

/**
 * A node's drawn radius: the seed is fixed-large; everything else scales
 * gently with citation count, capped so megahits don't swallow the canvas.
 */
export function nodeRadius(node: GraphNode): number {
  if (node.is_seed) return 10
  const c = node.citation_count ?? 0
  return Math.min(3 + Math.sqrt(c) / 6, 18)
}

/**
 * Strip a live VNode back to its persistable GraphNode fields — dropping the
 * sim's x/y and any fx/fy pins (re-derived on restore), and the researcher's
 * `idx` (per-conversation numbering ephemera; the researcher renumbers from node
 * order on every question, so persisting it would only mislead).
 */
export function cleanNode(n: VNode): GraphNode {
  return {
    id: n.id,
    arxiv_id: n.arxiv_id,
    title: n.title,
    abstract: n.abstract,
    tldr: n.tldr,
    year: n.year,
    month: n.month,
    pub_date: n.pub_date,
    citation_count: n.citation_count,
    authors: n.authors,
    url: n.url,
    rels: n.rels,
    is_seed: n.is_seed,
    discovered: n.discovered,
  }
}

/**
 * Rebuild a GraphResponse's relation counts from its nodes — used when
 * restoring a saved session (whose stored node set already includes
 * discovered papers).
 */
export function countRels(nodes: GraphNode[]): GraphResponse['counts'] {
  const c = { references: 0, citations: 0, similar: 0, nodes: nodes.length }
  nodes.forEach((n) =>
    n.rels.forEach((r) => {
      if (r === 'reference') c.references++
      else if (r === 'citation') c.citations++
      else if (r === 'similar') c.similar++
    }),
  )
  return c
}
