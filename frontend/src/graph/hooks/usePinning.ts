/**
 * Pin state for the explorer: which nodes the user has fixed in place, plus
 * the drag / toggle / release handlers that set and clear fx/fy on the live
 * simulation nodes.
 *
 * Timeline-aware throughout: in Timeline mode a node's x always stays pinned
 * to its date column — dragging only sets its height, and releasing restores
 * the column pin rather than freeing the node entirely.
 */

import { useCallback, useEffect, useState } from 'react'
import type { Base, VNode } from '../model'

/** Arguments for {@link usePinning}. */
export interface UsePinningArgs {
  /** The stable per-graph dataset whose node objects carry the fx/fy pins. */
  base: Base | null
  /** The current layout mode (release semantics differ in Timeline). */
  layout: 'force' | 'timeline'
  /** A node's date-column x (from useTimeline), for Timeline-mode re-pinning. */
  nodeTimelineX: (node: { year: number | null; month?: number | null }) => number
  /** The ForceGraph2D ref, to reheat the sim after releasing pins. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fgRef: { current: any }
}

/** What {@link usePinning} returns for GraphExplorer to wire up. */
export interface PinningApi {
  /** Ids of the nodes the user has pinned. */
  pinned: Set<string>
  /** Clear pin STATE only (layout switches re-pin the nodes themselves). */
  clearPins: () => void
  /** Drag-release handler: pin the node where it was dropped. */
  onNodeDragEnd: (node: VNode) => void
  /** Pin a node at its current position, or release it if already pinned. */
  togglePin: (id: string) => void
  /** Unpin every node (keeps Timeline date columns when in Timeline). */
  releaseAll: () => void
}

/**
 * Own the pinned-node state and the fx/fy mutations behind it.
 *
 * Pin state resets whenever a new graph loads (the fresh node objects carry
 * no pins).
 *
 * @returns The pinned-id set + the pin/unpin/release handlers.
 */
export function usePinning({ base, layout, nodeTimelineX, fgRef }: UsePinningArgs): PinningApi {
  const [pinned, setPinned] = useState<Set<string>>(new Set())

  // A new graph starts unpinned.
  useEffect(() => {
    setPinned(new Set())
  }, [base])

  const clearPins = useCallback(() => setPinned(new Set()), [])

  const onNodeDragEnd = useCallback(
    (node: VNode) => {
      if (layout === 'timeline') {
        // Keep the paper at its date column; the drag only sets its height.
        node.fx = nodeTimelineX(node)
        node.fy = node.y
      } else {
        node.fx = node.x
        node.fy = node.y
      }
      setPinned((prev) => new Set(prev).add(node.id))
    },
    [layout, nodeTimelineX],
  )

  const togglePin = useCallback(
    (id: string) => {
      if (!base) return
      const node = base.nodes.find((candidate) => candidate.id === id)
      if (!node) return
      if (pinned.has(id)) {
        // Unpin: in Timeline, keep the date-column x-pin; in Force, fully release.
        node.fx = layout === 'timeline' ? nodeTimelineX(node) : undefined
        node.fy = undefined
        setPinned((prev) => {
          const next = new Set(prev)
          next.delete(id)
          return next
        })
        fgRef.current?.d3ReheatSimulation?.()
      } else {
        node.fx = node.x
        node.fy = node.y
        setPinned((prev) => new Set(prev).add(id))
      }
    },
    [base, pinned, layout, nodeTimelineX, fgRef],
  )

  const releaseAll = useCallback(() => {
    base?.nodes.forEach((node) => {
      // Clearing user pins keeps the timeline structure (re-pin x by date).
      node.fx = base && layout === 'timeline' ? nodeTimelineX(node) : undefined
      node.fy = undefined
    })
    setPinned(new Set())
    // Deliberately NOT resetting the fitDone latch: Release re-settles the
    // layout under the user's current camera. Re-arming it made the engine
    // stop re-run zoomToFit, yanking the zoom out to the whole graph —
    // exactly the "reheat without camera yank" rule discoveries follow.
    fgRef.current?.d3ReheatSimulation?.()
  }, [base, layout, nodeTimelineX, fgRef])

  return { pinned, clearPins, onNodeDragEnd, togglePin, releaseAll }
}
