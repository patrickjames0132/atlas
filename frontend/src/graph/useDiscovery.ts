/**
 * Mid-conversation graph growth: the papers the AI teacher pulls in via its
 * expand_node / search_papers tools (and the history lecture's backward
 * walk), merged into the live graph without disturbing the simulation.
 *
 * The core constraint: `base`'s node/link objects are mutated by
 * react-force-graph (x/y) and by user pins (fx/fy), so discoveries must be
 * merged IN PLACE — appending to base.nodes/links, never rebuilding — and a
 * version counter signals dependents to recompute despite `base` keeping the
 * same object identity.
 */

import { useCallback, useEffect, useState } from 'react'
import type { GraphEdge, GraphNode } from '../api'
import type { Base, VNode } from './model'

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
  onYearLo: (y: number) => void
  onYearHi: (y: number) => void
}

/** What {@link useDiscovery} returns for GraphExplorer to wire up. */
export interface DiscoveryApi {
  /**
   * Papers the agent has pulled in this session. Mirrors what's been pushed
   * into `base.nodes` — kept separately so it can extend the teacher's
   * grounding context on follow-up questions without forcing `base` to
   * rebuild (which would drop the sim's x/y on every node).
   */
  discoveredNodes: GraphNode[]
  /**
   * Bumped whenever base.nodes/links are mutated in place, so the filtered
   * view (and anything else keyed on it) recomputes despite `base` itself
   * keeping the same object identity.
   */
  graphVersion: number
  /** Merge a discovery event's nodes + edges into the live graph. */
  onDiscover: (newNodes: GraphNode[], newEdges: GraphEdge[]) => void
}

/**
 * Own the agent-discovery state and the in-place `base` merge.
 *
 * On a new graph the state resets — usually to empty, but a restored session's
 * node set already carries its discovered papers, which are re-collected here.
 */
export function useDiscovery({
  base,
  layout,
  nodeTimelineX,
  fgRef,
  onYearLo,
  onYearHi,
}: UseDiscoveryArgs): DiscoveryApi {
  const [discoveredNodes, setDiscoveredNodes] = useState<GraphNode[]>([])
  const [graphVersion, setGraphVersion] = useState(0)

  // Reset per graph. Usually empty (discoveries arrive later via onDiscover);
  // on a restored session the saved node set already carries its discovered
  // papers.
  useEffect(() => {
    if (!base) return
    setDiscoveredNodes(base.nodes.filter((n) => n.discovered))
    setGraphVersion(0)
  }, [base])

  const onDiscover = useCallback(
    (newNodes: GraphNode[], newEdges: GraphEdge[]) => {
      if (!base || (newNodes.length === 0 && newEdges.length === 0)) return
      const knownIds = new Set(base.nodes.map((n) => n.id))
      const addedNodes: GraphNode[] = []
      for (const n of newNodes) {
        if (knownIds.has(n.id)) continue
        knownIds.add(n.id)
        // Start near whichever already-placed node it was discovered from, so
        // it doesn't fly in from the origin when the sim reheats. Topic-search
        // hits have no edge (ungrounded) — anchor them on the seed and scatter
        // wider so they settle into a loose cluster instead of stacking on it.
        const anchorEdge = newEdges.find((e) => e.source === n.id || e.target === n.id)
        const anchorId = anchorEdge
          ? anchorEdge.source === n.id
            ? anchorEdge.target
            : anchorEdge.source
          : null
        const anchor = anchorId
          ? base.nodes.find((x) => x.id === anchorId)
          : base.nodes.find((x) => x.is_seed)
        const spread = anchorEdge ? 40 : 120
        const vn: VNode = { ...n }
        if (anchor && typeof anchor.x === 'number' && typeof anchor.y === 'number') {
          vn.x = anchor.x + (Math.random() - 0.5) * spread
          vn.y = anchor.y + (Math.random() - 0.5) * spread
        }
        if (layout === 'timeline') vn.fx = nodeTimelineX(vn)
        base.nodes.push(vn)
        addedNodes.push(n)
        n.rels.forEach((r) => {
          if (r in base.counts) base.counts[r]++
        })
        // A discovery older/newer than anything on the graph widens both the
        // base's year range and the active filter, so it stays visible.
        if (typeof n.year === 'number') {
          if (n.year < base.minYear) {
            base.minYear = n.year
            onYearLo(n.year)
          }
          if (n.year > base.maxYear) {
            base.maxYear = n.year
            onYearHi(n.year)
          }
        }
      }

      const knownLinkKeys = new Set(base.links.map((l) => `${l._s}|${l._t}|${l.type}`))
      let addedLinks = 0
      for (const e of newEdges) {
        const key = `${e.source}|${e.target}|${e.type}`
        if (knownLinkKeys.has(key)) continue
        knownLinkKeys.add(key)
        base.links.push({ ...e, _s: e.source, _t: e.target })
        addedLinks++
      }

      if (addedNodes.length) setDiscoveredNodes((prev) => [...prev, ...addedNodes])
      if (addedNodes.length || addedLinks) {
        setGraphVersion((v) => v + 1)
        // Reheat so new nodes settle into place, but don't yank the camera —
        // the user may be mid-conversation, not looking at the graph.
        fgRef.current?.d3ReheatSimulation?.()
      }
    },
    [base, layout, nodeTimelineX, fgRef, onYearLo, onYearHi],
  )

  return { discoveredNodes, graphVersion, onDiscover }
}
