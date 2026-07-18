/**
 * The Force layout's relation clustering: a custom d3 force that pulls every
 * neighbor toward an angular sector around the seed, one sector per relation,
 * so the neighborhood reads as distinct clusters instead of one
 * undifferentiated cloud (the Force-layout counterpart to Timeline's
 * separation by date).
 *
 * Geometry: each relation owns a fixed compass heading (stable across graphs,
 * so the map always reads the same way) — references west, echoing Timeline's
 * past-is-left; the two citing relations east (landmarks up, latest down);
 * the researcher's discoveries on the remaining diagonals. A cluster's orbit
 * radius grows with the square root of its population (area scales linearly
 * with the papers in it), which spaces big clusters farther from the seed —
 * and from each other — while small ones stay close. Anchors are computed
 * from the seed's LIVE position every tick, so the whole formation follows
 * if the seed drifts or is dragged.
 *
 * Wired up (with the matching collide force and per-type link distances) in
 * `hooks/useTimeline.ts`'s `applyLayoutPhysics`, the one owner of the sim's
 * d3 forces.
 */

import { primaryRel } from './model'
import type { VNode } from './model'

/**
 * Each relation's compass heading around the seed, in radians (canvas y grows
 * downward). References west — the past on the left, matching Timeline —
 * citing relations east (landmarks up-right, latest down-right), the
 * researcher's discoveries on the west diagonals (similar up, search down).
 */
const SECTOR_ANGLE: Record<string, number> = {
  reference: Math.PI,
  citation: -Math.PI / 3,
  latest: Math.PI / 3,
  similar: (-3 * Math.PI) / 4,
  search: (3 * Math.PI) / 4,
}

/** The smallest cluster orbit — clear air between the seed and any cluster. */
const BASE_RADIUS = 170
/** Orbit growth per √(cluster population) — area scales with the papers. */
const RADIUS_PER_NODE = 20
/** How hard a node accelerates toward its cluster anchor (per unit alpha). */
const PULL = 0.08

/**
 * A cluster's orbit radius for its population.
 *
 * @param count Papers in the cluster.
 * @returns The anchor's distance from the seed, in graph units.
 */
export function clusterRadius(count: number): number {
  return BASE_RADIUS + RADIUS_PER_NODE * Math.sqrt(count)
}

/**
 * Per-relation cluster populations (by each node's primary relation, the same
 * one that colors it — a multi-relation node clusters where it's painted).
 *
 * @param nodes The sim's nodes.
 * @returns Population per relation key.
 */
export function clusterCounts(nodes: VNode[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const node of nodes) {
    if (node.is_seed) continue
    const rel = primaryRel(node)
    counts[rel] = (counts[rel] ?? 0) + 1
  }
  return counts
}

/**
 * Build the clustering force. d3 contract: a function of `alpha` with an
 * `initialize(nodes)` the simulation calls whenever its node list changes —
 * which is where the seed handle and per-cluster radii refresh, so filter
 * changes and mid-conversation discoveries re-balance the orbits for free.
 *
 * @returns The custom force, ready for `fg.d3Force('cluster', ...)`.
 */
export function clusterForce() {
  let nodes: VNode[] = []
  let seed: VNode | undefined
  let radii: Record<string, number> = {}

  const force = (alpha: number) => {
    if (!seed || typeof seed.x !== 'number' || typeof seed.y !== 'number') return
    for (const node of nodes) {
      if (node.is_seed) continue
      const rel = primaryRel(node)
      const angle = SECTOR_ANGLE[rel]
      if (angle === undefined) continue
      const orbit = radii[rel] ?? BASE_RADIUS
      const targetX = seed.x + Math.cos(angle) * orbit
      const targetY = seed.y + Math.sin(angle) * orbit
      node.vx = (node.vx ?? 0) + (targetX - (node.x ?? 0)) * PULL * alpha
      node.vy = (node.vy ?? 0) + (targetY - (node.y ?? 0)) * PULL * alpha
    }
  }
  force.initialize = (simNodes: VNode[]) => {
    nodes = simNodes
    seed = simNodes.find((node) => node.is_seed)
    radii = Object.fromEntries(
      Object.entries(clusterCounts(simNodes)).map(([rel, count]) => [rel, clusterRadius(count)]),
    )
  }
  return force
}
