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
 * positions and pins survive), plus the year range, per-relation counts, and
 * the citation-count range (the citation slider's bounds).
 */
export type Base = {
  nodes: VNode[]
  links: VLink[]
  minYear: number
  maxYear: number
  counts: Record<string, number>
  minCitations: number
  maxCitations: number
}

/** Discrete positions along each knob of the citation-count window slider — a
 * smooth log sweep from the graph's least-cited paper (position 0) to its
 * most-cited (the top position). */
export const CITE_SLIDER_STEPS = 100

/**
 * Map a citation-slider knob position to the citation count it represents. Both
 * knobs of the citation window use this (the low knob's count is the floor, the
 * high knob's the ceiling), and — like the year slider's min/max year bounds —
 * the sweep spans the graph's actual citation range, so neither knob has dead
 * travel below the least-cited paper or above the most-cited. The scale is
 * logarithmic because citation counts fan out over orders of magnitude (a
 * handful of giants, a long tail of ones and zeros): a linear slider would
 * spend almost its whole travel among a few citations. `log1p`/`expm1` anchor
 * the ends exactly — position 0 yields `minCitations`, the top `maxCitations`.
 *
 * @param position     The knob position, 0…{@link CITE_SLIDER_STEPS}.
 * @param minCitations The lowest citation count in the graph (the floor).
 * @param maxCitations The highest citation count in the graph (the ceiling).
 * @returns The citation count for the current knob position.
 */
export function citationThreshold(
  position: number,
  minCitations: number,
  maxCitations: number,
): number {
  const low = Math.log1p(Math.max(0, minCitations))
  const high = Math.log1p(Math.max(0, maxCitations))
  if (high <= low) return maxCitations
  const frac = Math.min(Math.max(position, 0), CITE_SLIDER_STEPS) / CITE_SLIDER_STEPS
  return Math.round(Math.expm1(low + frac * (high - low)))
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * Human-readable publication date: "Jun 12, 2017" from a "YYYY-MM-DD" string,
 * gracefully degrading to "Jun 2017" / the year / "—" as data thins out.
 *
 * Parsed by hand (not `new Date`) to avoid timezone off-by-one on date-only
 * strings.
 *
 * @param pubDate The paper's "YYYY-MM-DD" (or "YYYY-MM") date, when known.
 * @param year    The bare publication year, the fallback.
 * @returns The formatted date, or "—" when nothing is known.
 */
export function formatPubDate(pubDate?: string | null, year?: number | null): string {
  if (pubDate) {
    const match = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(pubDate)
    if (match) {
      const mon = MONTHS[Number(match[2]) - 1]
      if (mon && match[3]) return `${mon} ${Number(match[3])}, ${match[1]}`
      if (mon) return `${mon} ${match[1]}`
      return match[1]
    }
  }
  return year != null ? String(year) : '—'
}

/**
 * The single relation that decides a node's color: seed wins, then the first
 * graph relation in priority order, then topic-search hits get their own
 * color, falling back to 'similar'.
 *
 * @param node The paper node.
 * @returns The relation key into `REL_COLOR`.
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
 *
 * @param node The paper node.
 * @returns The radius in graph units.
 */
export function nodeRadius(node: GraphNode): number {
  if (node.is_seed) return 10
  const citations = node.citation_count ?? 0
  return Math.min(3 + Math.sqrt(citations) / 6, 18)
}

/**
 * Ids of the nodes matching a local find query — case-insensitive substring
 * over the title and the (formatted) author string. Purely lexical and local:
 * this powers the controls' find box, which spotlights papers already on
 * screen — the header's seed search is the one that fetches new ones.
 *
 * @param nodes The candidate nodes (pass the *visible* view, so hidden papers
 *              can't match invisibly).
 * @param query The raw box contents.
 * @returns The matching ids — possibly empty (dim everything: honest feedback
 *          for "no hits") — or null when the trimmed query is empty (no find
 *          active at all).
 */
export function findMatches(nodes: GraphNode[], query: string): Set<string> | null {
  const needle = query.trim().toLowerCase()
  if (!needle) return null
  const matches = new Set<string>()
  nodes.forEach((node) => {
    const haystack = `${node.title} ${node.authors ?? ''}`.toLowerCase()
    if (haystack.includes(needle)) matches.add(node.id)
  })
  return matches
}

/**
 * Strip a live VNode back to its persistable GraphNode fields — dropping the
 * sim's x/y and any fx/fy pins (re-derived on restore), and the researcher's
 * `idx` (per-conversation numbering ephemera; the researcher renumbers from node
 * order on every question, so persisting it would only mislead).
 *
 * @param node The live simulation node.
 * @returns The bare persistable `GraphNode`.
 */
export function cleanNode(node: VNode): GraphNode {
  return {
    id: node.id,
    arxiv_id: node.arxiv_id,
    title: node.title,
    abstract: node.abstract,
    tldr: node.tldr,
    year: node.year,
    month: node.month,
    pub_date: node.pub_date,
    citation_count: node.citation_count,
    authors: node.authors,
    url: node.url,
    rels: node.rels,
    is_seed: node.is_seed,
    discovered: node.discovered,
  }
}

/**
 * Rebuild a GraphResponse's relation counts from its nodes — used when
 * restoring a saved session (whose stored node set already includes
 * discovered papers).
 *
 * @param nodes The restored nodes.
 * @returns Per-relation totals plus the node count.
 */
export function countRels(nodes: GraphNode[]): GraphResponse['counts'] {
  const counts = { references: 0, citations: 0, similar: 0, latest: 0, nodes: nodes.length }
  nodes.forEach((node) =>
    node.rels.forEach((rel) => {
      if (rel === 'reference') counts.references++
      else if (rel === 'citation') counts.citations++
      else if (rel === 'similar') counts.similar++
      else if (rel === 'latest') counts.latest++
    }),
  )
  return counts
}
