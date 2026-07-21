/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
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
 * Expansion satellites are the exception (v5.24.0): a discovery carrying a
 * graph relation used to be absorbed into the seed's matching sector, tearing
 * it away from the node it was expanded from. A node with an `_origin` (set
 * by useDiscovery's merge when its anchor isn't the seed) skips the sectors
 * and gathers just BEYOND its origin instead — on the ray from the seed
 * through the origin, so each expansion reads as its own mini-cluster pushed
 * outward from the formation, with its own √population spacing.
 *
 * Wired up (with the matching collide force and per-type link distances) in
 * `hooks/useTimeline.ts`'s `applyLayoutPhysics`, the one owner of the sim's
 * d3 forces.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
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
/** How far beyond its origin node an expansion's satellites gather. */
const SATELLITE_OFFSET = 90
/** Satellite-cluster growth per √population — smaller groups, tighter. */
const SATELLITE_RADIUS_PER_NODE = 12
/** Satellite pull — a touch stronger than the sectors', so a small group
 *  stays visibly gathered against the big clusters' collide pressure. */
const SATELLITE_PULL = 0.12

/** A discovery-cluster's distance beyond its origin node.
 *
 * @param count Satellites sharing the origin.
 * @returns The anchor's distance past the origin, in graph units.
 */
export function satelliteOffset(count: number): number {
  return SATELLITE_OFFSET + SATELLITE_RADIUS_PER_NODE * Math.sqrt(count)
}

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
    if (node.is_seed || node._origin) continue // satellites orbit their origin, not a sector
    const rel = primaryRel(node)
    counts[rel] = (counts[rel] ?? 0) + 1
  }
  return counts
}

/**
 * Re-derive `_origin` for a RESTORED graph's discovered nodes. A live
 * discovery gets its origin stamped by useDiscovery's merge, but a save
 * folds discoveries into the graph itself, so a reopened session arrives
 * with plain `discovered` nodes and no stamps — without this, satellites
 * would silently fall back into the seed's sectors after every restore.
 * Same rule as the live merge: the origin is the other endpoint of the
 * node's first edge, when that endpoint isn't the seed.
 *
 * @param nodes The freshly built sim nodes (mutated in place).
 * @param links The sim links (`_s`/`_t` raw endpoint ids).
 * @param seedId The graph's seed id (a seed-anchored discovery is no satellite).
 */
export function deriveOrigins(
  nodes: VNode[],
  links: { _s: string; _t: string }[],
  seedId: string,
): void {
  for (const node of nodes) {
    if (!node.discovered) continue
    const edge = links.find((link) => link._s === node.id || link._t === node.id)
    if (!edge) continue
    const other = edge._s === node.id ? edge._t : edge._s
    if (other !== seedId) node._origin = other
  }
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
  let byId: Map<string, VNode> = new Map()
  let satelliteCounts: Record<string, number> = {}

  const force = (alpha: number) => {
    if (!seed || typeof seed.x !== 'number' || typeof seed.y !== 'number') return
    for (const node of nodes) {
      if (node.is_seed) continue
      // Expansion satellite: gather just beyond the origin node, on the ray
      // from the seed through it — pushed outward from the formation, and
      // following the origin's live position wherever its sector settles it.
      // An origin hidden by the filters falls through to sector behavior.
      const origin = node._origin ? byId.get(node._origin) : undefined
      if (origin && typeof origin.x === 'number' && typeof origin.y === 'number') {
        const rayX = origin.x - seed.x
        const rayY = origin.y - seed.y
        const rayLen = Math.hypot(rayX, rayY) || 1
        const offset = satelliteOffset(satelliteCounts[node._origin!] ?? 1)
        const targetX = origin.x + (rayX / rayLen) * offset
        const targetY = origin.y + (rayY / rayLen) * offset
        node.vx = (node.vx ?? 0) + (targetX - (node.x ?? 0)) * SATELLITE_PULL * alpha
        node.vy = (node.vy ?? 0) + (targetY - (node.y ?? 0)) * SATELLITE_PULL * alpha
        continue
      }
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
    byId = new Map(simNodes.map((node) => [node.id, node]))
    radii = Object.fromEntries(
      Object.entries(clusterCounts(simNodes)).map(([rel, count]) => [rel, clusterRadius(count)]),
    )
    satelliteCounts = {}
    for (const node of simNodes) {
      if (node._origin) satelliteCounts[node._origin] = (satelliteCounts[node._origin] ?? 0) + 1
    }
  }
  return force
}
