/**
 * The Timeline layout machinery, as a hook: pinning each node's x to its
 * publication year, the collide force that spreads a year column out, the
 * year-axis painter, and the effects that keep all of it in sync as graphs
 * load and the year slider moves.
 *
 * State (layout mode, pins) stays in GraphExplorer — this hook only mutates
 * the simulation's node objects and d3 forces through the shared `fgRef`,
 * exactly as the inline code it replaced did.
 */

import { useCallback, useEffect } from 'react'
// react-force-graph's own force lib (d3-force-3d) ships no types; we only need
// forceCollide to space timeline nodes out by their radius.
// @ts-expect-error - no type declarations
import { forceCollide } from 'd3-force-3d'
import { nodeRadius } from './model'
import type { Base, VNode } from './model'
import { YEAR_SPACING } from './theme'

/** Arguments for {@link useTimeline}. */
export interface UseTimelineArgs {
  /** The stable per-graph dataset whose node objects the sim mutates. */
  base: Base | null
  /** The current layout mode. */
  layout: 'force' | 'timeline'
  /** The ForceGraph2D ref (for d3 forces, reheat, zoomToFit, coords). */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fgRef: { current: any }
  /** The canvas size (drawAxis spans the visible viewport). */
  size: { w: number; h: number }
  /** Shared "zoomToFit already ran for this layout" latch. */
  fitDone: { current: boolean }
  /** The selected year window (Timeline refits when it changes). */
  yearLo: number
  yearHi: number
}

/** What {@link useTimeline} returns for GraphExplorer to wire up. */
export interface TimelineApi {
  /**
   * A node's timeline x: its year plus a month fraction, so papers sit
   * *between* the yearly gridlines by publication month (unknown month →
   * start of year; no year → an "n.d." lane left of the earliest year).
   */
  nodeTimelineX: (node: { year: number | null; month?: number | null }) => number
  /**
   * Apply a layout's physics: Timeline pins every node's x to its year column
   * and adds a radius-sized collide force; Force releases the pins and the
   * collide. Does NOT touch pin state — the caller clears `pinned` itself.
   */
  applyLayoutPhysics: (mode: 'force' | 'timeline') => void
  /**
   * Paint the year axis behind the graph in Timeline mode: a faint gridline +
   * label per year, thinned out when zoomed too far to fit them all. Passed
   * to ForceGraph2D's `onRenderFramePre`.
   */
  drawAxis: (ctx: CanvasRenderingContext2D, globalScale: number) => void
  /**
   * Once the sim settles in Timeline, freeze y as well (x is already pinned
   * by year) so the layout is stable and dragging one node can't re-relax
   * the rest. Called from the engine-stop handler; no-ops in Force mode.
   */
  freezeSettledY: (pinned: Set<string>) => void
}

/**
 * Own the Timeline layout's physics and painting for GraphExplorer.
 *
 * Also runs two effects: re-pinning year columns when a new graph loads while
 * Timeline is active, and refitting the camera when the year slider narrows.
 */
export function useTimeline({
  base,
  layout,
  fgRef,
  size,
  fitDone,
  yearLo,
  yearHi,
}: UseTimelineArgs): TimelineApi {
  // Map a year to its gridline x on the timeline. Papers with no year sit in
  // an "n.d." lane just left of the earliest year.
  const yearToX = useCallback(
    (year: number | null | undefined) => {
      if (!base) return 0
      const y = typeof year === 'number' ? year : base.minYear - 1
      return (y - base.minYear) * YEAR_SPACING
    },
    [base],
  )

  const nodeTimelineX = useCallback(
    (node: { year: number | null; month?: number | null }) => {
      if (!base) return 0
      const y = typeof node.year === 'number' ? node.year : base.minYear - 1
      const frac = typeof node.month === 'number' ? (node.month - 1) / 12 : 0
      return (y - base.minYear + frac) * YEAR_SPACING
    },
    [base],
  )

  const applyLayoutPhysics = useCallback(
    (mode: 'force' | 'timeline') => {
      if (!base) return
      base.nodes.forEach((n) => {
        if (mode === 'timeline') {
          n.fx = nodeTimelineX(n)
          n.fy = undefined
        } else {
          n.fx = undefined
          n.fy = undefined
        }
      })
      // Timeline: a collision force sized to each node's radius spreads papers
      // apart within a year column (no overlap, even spacing) rather than
      // letting them clump. Force mode keeps the default (no collide).
      const fg = fgRef.current
      const charge = fg?.d3Force?.('charge')
      if (charge) charge.strength(-30)
      fg?.d3Force?.(
        'collide',
        mode === 'timeline' ? forceCollide((n: VNode) => nodeRadius(n) + 6) : null,
      )
      fitDone.current = false
      fg?.d3ReheatSimulation?.()
    },
    [base, nodeTimelineX, fgRef, fitDone],
  )

  // Re-pin x by year when a new graph loads while Timeline is active (a fresh
  // graph has no user pins yet, so every node gets its year column).
  useEffect(() => {
    if (!base || layout !== 'timeline') return
    applyLayoutPhysics('timeline')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base])

  // In Timeline, refit when the visible year range changes so narrowing the
  // slider zooms into those years — bigger nodes, less empty space.
  useEffect(() => {
    if (layout !== 'timeline') return
    const id = setTimeout(() => fgRef.current?.zoomToFit(400, 60), 150)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, yearLo, yearHi])

  const drawAxis = useCallback(
    (ctx: CanvasRenderingContext2D, globalScale: number) => {
      const fg = fgRef.current
      if (layout !== 'timeline' || !base || !fg || base.maxYear <= base.minYear)
        return
      const tl = fg.screen2GraphCoords(0, 0)
      const br = fg.screen2GraphCoords(size.w, size.h)
      // Only label as many years as comfortably fit (≥28px apart on screen).
      const px = YEAR_SPACING * globalScale
      const step = px < 28 ? Math.ceil(28 / px) : 1
      ctx.save()
      ctx.font = `${11 / globalScale}px -apple-system, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.lineWidth = 1 / globalScale
      for (let yr = base.minYear; yr <= base.maxYear; yr++) {
        if ((yr - base.minYear) % step !== 0) continue
        const x = yearToX(yr)
        ctx.strokeStyle = 'rgba(120,130,150,0.12)'
        ctx.beginPath()
        ctx.moveTo(x, tl.y)
        ctx.lineTo(x, br.y)
        ctx.stroke()
        ctx.fillStyle = 'rgba(150,160,180,0.65)'
        ctx.fillText(String(yr), x, tl.y + 4 / globalScale)
      }
      ctx.restore()
    },
    [layout, base, size, yearToX, fgRef],
  )

  const freezeSettledY = useCallback(
    (pinned: Set<string>) => {
      if (layout !== 'timeline' || !base) return
      base.nodes.forEach((n) => {
        if (!pinned.has(n.id) && typeof n.y === 'number') n.fy = n.y
      })
    },
    [layout, base],
  )

  return { nodeTimelineX, applyLayoutPhysics, drawAxis, freezeSettledY }
}
