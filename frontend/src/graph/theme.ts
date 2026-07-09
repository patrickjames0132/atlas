/**
 * Visual constants for the graph explorer: the relation color scheme shared by
 * nodes, edges, filter chips, badges, and the legend, plus layout geometry.
 *
 * Kept in one place so the canvas painting and the DOM chrome can never drift
 * out of sync on what "a reference" looks like.
 */

import type { EdgeType } from '../api'

/** Node fill per relation role — also used by filter chips, badges, legend. */
export const REL_COLOR: Record<string, string> = {
  seed: '#ffd166', // gold — the paper you're exploring
  reference: '#6ea8fe', // blue — ancestors it cites
  citation: '#4ade80', // green — landmark descendants that cite it
  latest: '#86efac', // light green — recent citers (the recent-years frontier)
  similar: '#c084fc', // purple — embedding-similar papers
  search: '#f472b6', // pink — pulled in by the teacher's topic search (3c.2)
}

/** Edge stroke per edge type (translucent versions of the node colors). */
export const EDGE_COLOR: Record<EdgeType, string> = {
  reference: 'rgba(110,168,254,0.30)',
  citation: 'rgba(74,222,128,0.30)',
  latest: 'rgba(134,239,172,0.32)',
  similar: 'rgba(192,132,252,0.24)',
}

/** Fill for nodes outside the current hover/highlight focus. */
export const DIM_NODE = 'rgba(120,130,150,0.18)'
/** Stroke for edges outside the current hover/highlight focus. */
export const DIM_EDGE = 'rgba(120,130,150,0.05)'

/**
 * Timeline layout: graph-x units per publication year. Wide enough that year
 * columns read as distinct; zoomToFit handles the overall scale.
 */
export const YEAR_SPACING = 120

/** The relation types the user can filter by (seed/search are always shown). */
export const REL_TYPES = ['reference', 'citation', 'latest', 'similar'] as const

/** Display labels for the filter chips. The two citing relations read as the
 * two halves of "Citations" (grouped under that heading in GraphControls). */
export const REL_LABEL: Record<string, string> = {
  reference: 'References',
  citation: 'Field Landmarks',
  latest: 'Latest Publications',
  similar: 'Similar',
}

/**
 * Where each relation's count slider starts when a graph loads (clamped to what
 * the paper actually has). The backend ships the whole ranked pool per relation
 * and each slider's MAX is that relation's available count; this is just the
 * modest initial position so a fresh graph isn't overwhelming.
 */
export const REL_DEFAULT_LIMIT: Record<(typeof REL_TYPES)[number], number> = {
  reference: 25,
  citation: 25,
  latest: 25,
  similar: 25,
}
