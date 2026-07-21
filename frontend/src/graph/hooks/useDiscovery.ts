/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Mid-conversation graph growth: the papers the AI teacher pulls in via its
 * expand_node / search_papers tools (and the history lecture's backward
 * walk), merged into the live graph without disturbing the simulation.
 *
 * The core constraint: `base`'s node/link objects are mutated by
 * react-force-graph (x/y) and by user pins (fx/fy), so discoveries must be
 * merged IN PLACE — appending to base.nodes/links, never rebuilding — and a
 * version counter signals dependents to recompute despite `base` keeping the
 * same object identity.
 *
 * The merge also decides a discovery's layout identity (v5.24.0): one whose
 * anchor edge lands on a NON-seed node is an expansion satellite — its
 * `_origin` records that node, and the cluster force gathers it beyond the
 * origin instead of absorbing it into the seed's relation sectors. In
 * Timeline (x date-pinned), satellites band outward in y past their origin
 * instead. Ungrounded/seed-anchored discoveries keep the old behavior.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useState } from 'react'
import type { GraphEdge, GraphNode } from '../../api'
import type { Base, VNode } from '../model'

/** Arguments for {@link useDiscovery}. */
export interface UseDiscoveryArgs {
  /** The stable per-graph dataset discoveries are merged into (in place). */
  base: Base | null
  /** The current layout mode (Timeline pins a discovery's x to its year). */
  layout: 'force' | 'timeline'
  /** A node's date-column x (from useTimeline), for Timeline placement. */
  nodeTimelineX: (node: { year: number | null; month?: number | null }) => number
  /** The ForceGraph2D ref, to reheat the sim so new nodes settle in. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fgRef: { current: any }
  /** Widen the year filter when a discovery falls outside the current range. */
  onYearLo: (year: number) => void
  onYearHi: (year: number) => void
}

/** What {@link useDiscovery} returns for GraphExplorer to wire up. */
export interface DiscoveryApi {
  /**
   * Bumped whenever base.nodes/links are mutated in place, so the filtered
   * view (and anything else keyed on it) recomputes despite `base` itself
   * keeping the same object identity.
   */
  graphVersion: number
  /**
   * Merge discovery nodes + edges into the live graph. Dedupes internally,
   * so re-feeding the store's full discovery arrays is safe — only papers
   * not yet on the canvas are added. (The discovery LISTS live in the
   * workspace slice — grounding, save, and the legend read from there;
   * this hook owns only the sim-side merge.)
   */
  onDiscover: (newNodes: GraphNode[], newEdges: GraphEdge[]) => void
}

/**
 * Own the in-place `base` merge for agent discoveries.
 *
 * @returns The merge entry point + the `graphVersion` change counter.
 */
export function useDiscovery({
  base,
  layout,
  nodeTimelineX,
  fgRef,
  onYearLo,
  onYearHi,
}: UseDiscoveryArgs): DiscoveryApi {
  const [graphVersion, setGraphVersion] = useState(0)

  // Reset the version counter per graph.
  useEffect(() => {
    if (!base) return
    setGraphVersion(0)
  }, [base])

  const onDiscover = useCallback(
    (newNodes: GraphNode[], newEdges: GraphEdge[]) => {
      if (!base || (newNodes.length === 0 && newEdges.length === 0)) return
      const knownIds = new Set(base.nodes.map((node) => node.id))
      const addedNodes: GraphNode[] = []
      for (const node of newNodes) {
        if (knownIds.has(node.id)) continue
        knownIds.add(node.id)
        // Start near whichever already-placed node it was discovered from, so
        // it doesn't fly in from the origin when the sim reheats. Topic-search
        // hits have no edge (ungrounded) — anchor them on the seed and scatter
        // wider so they settle into a loose cluster instead of stacking on it.
        const anchorEdge = newEdges.find(
          (edge) => edge.source === node.id || edge.target === node.id,
        )
        const anchorId = anchorEdge
          ? anchorEdge.source === node.id
            ? anchorEdge.target
            : anchorEdge.source
          : null
        const anchor = anchorId
          ? base.nodes.find((candidate) => candidate.id === anchorId)
          : base.nodes.find((candidate) => candidate.is_seed)
        const spread = anchorEdge ? 40 : 120
        const viewNode: VNode = { ...node }
        // An expansion anchored on a NON-seed node is a satellite: mark its
        // origin so the cluster force gathers it beyond that node instead of
        // absorbing it into the seed's relation sectors (see clusterForce.ts).
        // Seed-anchored discoveries genuinely belong to the seed's sectors.
        if (anchor && anchorEdge && !anchor.is_seed) viewNode._origin = anchor.id
        if (anchor && typeof anchor.x === 'number' && typeof anchor.y === 'number') {
          viewNode.x = anchor.x + (Math.random() - 0.5) * spread
          viewNode.y = anchor.y + (Math.random() - 0.5) * spread
        }
        if (layout === 'timeline') {
          viewNode.fx = nodeTimelineX(viewNode)
          // Timeline can't separate satellites in x (it's date-pinned), so
          // they band OUTWARD in y instead: pushed past their origin's side
          // of the settled mass (whose heights are frozen — see
          // freezeSettledY), where the reheat lets them spread by collide
          // without landing inside the existing columns.
          if (viewNode._origin && anchor && typeof anchor.y === 'number') {
            const outward = Math.sign(anchor.y) || 1
            viewNode.y = anchor.y + outward * (120 + Math.random() * 60)
          }
        }
        base.nodes.push(viewNode)
        addedNodes.push(node)
        node.rels.forEach((rel) => {
          if (rel in base.counts) base.counts[rel]++
        })
        // A discovery older/newer than anything on the graph widens both the
        // base's year range and the active filter, so it stays visible.
        if (typeof node.year === 'number') {
          if (node.year < base.minYear) {
            base.minYear = node.year
            onYearLo(node.year)
          }
          if (node.year > base.maxYear) {
            base.maxYear = node.year
            onYearHi(node.year)
          }
        }
      }

      const knownLinkKeys = new Set(base.links.map((link) => `${link._s}|${link._t}|${link.type}`))
      let addedLinks = 0
      for (const edge of newEdges) {
        const key = `${edge.source}|${edge.target}|${edge.type}`
        if (knownLinkKeys.has(key)) continue
        knownLinkKeys.add(key)
        base.links.push({ ...edge, _s: edge.source, _t: edge.target })
        addedLinks++
      }

      if (addedNodes.length || addedLinks) {
        setGraphVersion((version) => version + 1)
        // Reheat so new nodes settle into place, but don't yank the camera —
        // the user may be mid-conversation, not looking at the graph.
        fgRef.current?.d3ReheatSimulation?.()
      }
    },
    [base, layout, nodeTimelineX, fgRef, onYearLo, onYearHi],
  )

  return { graphVersion, onDiscover }
}
