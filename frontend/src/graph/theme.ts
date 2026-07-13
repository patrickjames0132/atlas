/**
 * Visual constants for the graph explorer: the relation color scheme shared by
 * nodes, edges, filter chips, badges, and the legend, plus layout geometry.
 *
 * Kept in one place so the canvas painting and the DOM chrome can never drift
 * out of sync on what "a reference" looks like.
 */

import type { EdgeType } from '../api'

/** Node fill per relation role — also used by filter chips, legend, lecture
 * buttons. (Detail-panel badges use BADGE_COLOR, which keeps a lighter green
 * for `citation` — see below.) */
export const REL_COLOR: Record<string, string> = {
  seed: '#ffd166', // gold — the paper you're exploring
  reference: '#6ea8fe', // blue — ancestors it cites
  citation: '#22c55e', // green — landmark descendants that cite it (darkened a
  //                       shade to stand apart from `latest`'s pale green)
  latest: '#86efac', // light green — recent citers (the recent-years frontier)
  similar: '#c084fc', // purple — embedding-similar papers
  search: '#f472b6', // pink — pulled in by the teacher's topic search (3c.2)
}

/** Relation colours for the detail-panel badges. Mirrors REL_COLOR, but both
 * citing relations — Field Landmarks (`citation`) and Latest Publications
 * (`latest`) — read as one "citation" badge in the panel (see BADGE_LABEL), so
 * they share the one mid-green (#4ade80): now that the graph's landmark green is
 * darker, this in-between shade sits between it and `latest`'s pale green on the
 * graph, and reads clearly on the panel. */
export const BADGE_COLOR: Record<string, string> = {
  ...REL_COLOR,
  citation: '#4ade80',
  latest: '#4ade80',
}

/** Detail-panel badge text per relation, defaulting to the relation key. A
 * `latest` node reads as "citation" too — Latest Publications ARE citing
 * papers, just recent ones — so both citing relations show the one badge. */
export const BADGE_LABEL: Record<string, string> = {
  latest: 'citation',
}

/** Edge stroke per edge type (translucent versions of the node colors). */
export const EDGE_COLOR: Record<EdgeType, string> = {
  reference: 'rgba(110,168,254,0.30)',
  citation: 'rgba(34,197,94,0.30)',
  latest: 'rgba(134,239,172,0.32)',
  similar: 'rgba(192,132,252,0.24)',
}

/** Ring for a node hand-picked into the teacher's scope (the alt-drag marquee /
 * shift-click selection). Cyan — deliberately unlike the gold highlight, white
 * detail-selection, and pale-white pin rings, so a scoped node reads at a
 * glance while a selection is active. */
export const SELECTION_RING = '#22d3ee'

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
