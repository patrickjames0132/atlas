/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Visual constants for the graph explorer: the relation color scheme shared by
 * nodes, edges, filter chips, badges, and the legend, plus layout geometry.
 *
 * Kept in one place so the canvas painting and the DOM chrome can never drift
 * out of sync on what "a reference" looks like.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useTheme } from '../ui/theme'
import type { EdgeType } from '../api'

/** The theme-dependent colors the canvas paints with. */
export interface CanvasInk {
  /** Node labels and the discovered-node dashed ring. */
  ink: string
  /** The softer pinned-node ring. */
  soft: string
  /** The solid detail-selection ring. */
  hard: string
  /** The canvas backdrop — force-graph paints it itself, so it can't be CSS. */
  background: string
}

/**
 * The canvas's neutral inks for the active theme.
 *
 * The relation colors above are theme-independent (they carry meaning), but
 * labels and rings were hardcoded near-white — invisible on a light
 * background. Canvas painting is JS, so it can't inherit from a stylesheet:
 * this reads the computed `--canvas-*` custom properties instead, and
 * re-reads whenever the theme changes (the hook subscribes, so the component
 * re-renders and its painters close over fresh values).
 *
 * @returns The inks to paint labels and rings with.
 */
export function useCanvasInk(): CanvasInk {
  // Depend on the theme so a switch re-renders the caller; the values
  // themselves come from the CSS variables the theme just swapped.
  useTheme()
  const style = getComputedStyle(document.documentElement)
  const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback
  return {
    ink: read('--canvas-ink', 'rgba(231,236,245,0.9)'),
    soft: read('--canvas-ink-soft', 'rgba(242,244,248,0.55)'),
    hard: read('--canvas-ink-hard', '#f2f4f8'),
    background: read('--bg', '#0f1115'),
  }
}

/** Node fill per relation role — also used by filter chips, legend, lecture
 * buttons. (Detail-panel badges use BADGE_COLOR, which keeps a lighter green
 * for `citation` — see below.) */
export const REL_COLOR: Record<string, string> = {
  seed: '#ffd166', // gold — the paper you're exploring
  reference: '#6ea8fe', // blue — ancestors it cites
  citation: '#22c55e', // green — landmark descendants that cite it (darkened a
  //                       shade to stand apart from `latest`'s pale green)
  latest: '#86efac', // light green — recent citers (the recent-years frontier)
  // Grey — a node whose relations this build doesn't recognise. Not a relation
  // of its own: it's the catch-all that lets `primaryRel` stay total, and the
  // reason retiring a relation can never produce an uncoloured node. It also
  // renders the two retired ones — `search` (v7.3.0) and `similar` (v7.5.0) —
  // should a session saved before those changes turn up, which is the honest
  // treatment for a paper whose relation the app no longer has a meaning for.
  unknown: '#8b93a7',
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
}

/** Stroke for an edge whose type this build doesn't recognise — the edge twin
 * of `REL_COLOR.unknown`, and why a retired edge type can't draw an invisible
 * line on an old save. */
export const UNKNOWN_EDGE = 'rgba(139,147,167,0.22)'

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

/**
 * The relation types the user can filter by, in colour-priority order. `seed`
 * is always shown (no chip). Two relations used to sit alongside it here and
 * are gone entirely now: `search` (v7.3.0) and `similar` (v7.5.0), neither of
 * which can be created any more. A session saved before those changes still
 * carries them, and they fall through to `REL_COLOR.unknown` rather than to a
 * colour — and a chip — of their own.
 */
export const REL_TYPES = ['reference', 'citation', 'latest'] as const

/** Display labels for the filter chips. The two citing relations read as the
 * two halves of "Citations" (grouped under that heading in GraphControls). */
export const REL_LABEL: Record<string, string> = {
  reference: 'References',
  citation: 'Field Landmarks',
  latest: 'Latest Publications',
}
