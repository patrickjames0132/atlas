/**
 * The marquee node-selector: alt-drag a rectangle over the canvas to hand-pick
 * the nodes the AI teacher works over (its grounding scope). A modifier-drag,
 * not a mode — plain drag still pans the graph, so this arms only while Alt is
 * held and captures the drag through a transparent overlay so react-force-graph
 * never sees it (no pan fight). Shift-click single-node add/remove lives in
 * GraphExplorer's click handler; this owns the rectangle gesture.
 *
 * The marquee is **additive**: each alt-drag UNIONS the enclosed nodes onto the
 * current pick, so you can sweep several clusters into one scope. An alt-click
 * on empty canvas (a negligible drag) clears the pick, as does the controls'
 * Clear button. (We deliberately don't gate "add" behind Alt+Shift — that combo
 * is the OS keyboard-layout switch on Windows, which steals the modifier and
 * the window focus mid-drag.)
 *
 * Hit-testing runs in SCREEN space: `fgRef.graph2ScreenCoords` maps each
 * visible node's sim position to canvas-local pixels, compared against the
 * dragged rectangle (also canvas-local, measured off the wrap's bounding box —
 * the RFG canvas fills the wrap, so their top-lefts coincide).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent, RefObject } from 'react'
import { useAppDispatch } from '../../store'
import { nodeSelectionAdded, nodeSelectionCleared } from '../../store/workspace'
import type { VNode, VLink } from '../model'

/** A drag rectangle in wrap-local pixels, for painting the marquee outline. */
export interface MarqueeRect {
  left: number
  top: number
  width: number
  height: number
}

/** Arguments for {@link useMarquee}. */
export interface UseMarqueeArgs {
  /** The filtered live view — only visible nodes are eligible for a marquee. */
  view: { nodes: VNode[]; links: VLink[] }
  /** The ForceGraph2D instance ref (for `graph2ScreenCoords`). */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fgRef: { current: any }
  /** The canvas wrap element — the coordinate origin for the rectangle. */
  wrapRef: RefObject<HTMLDivElement | null>
}

/** What {@link useMarquee} returns for GraphExplorer to render. */
export interface MarqueeApi {
  /** True while Alt is held — the arm overlay is live and shows a crosshair. */
  armed: boolean
  /** The in-progress drag rectangle, or null when not dragging. */
  rect: MarqueeRect | null
  /** Mousedown handler for the arm overlay (starts an alt-drag). */
  onArmMouseDown: (event: ReactMouseEvent) => void
}

/** A drag below this many pixels in both axes counts as a click, not a
 *  rectangle — an alt-click on empty canvas, which clears the selection. */
const CLICK_SLOP = 3

/**
 * Own the alt-drag marquee: track when Alt arms the overlay, run the drag, and
 * union the enclosed node ids onto the selection on release.
 *
 * @param args The live view, the ForceGraph ref, and the wrap element ref.
 * @returns The arm/rect state and the overlay mousedown handler.
 */
export function useMarquee({ view, fgRef, wrapRef }: UseMarqueeArgs): MarqueeApi {
  const dispatch = useAppDispatch()
  const [armed, setArmed] = useState(false)
  const [rect, setRect] = useState<MarqueeRect | null>(null)
  // The view is read at mouseup, so keep the latest in a ref rather than
  // rebinding the (window-attached) drag handlers on every filter change.
  const viewRef = useRef(view)
  viewRef.current = view

  // Alt arms the overlay. A window blur (alt-tab) can swallow the keyup, so
  // reset on blur too, or the overlay would stay stuck capturing clicks.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Alt') setArmed(true)
    }
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key === 'Alt') setArmed(false)
    }
    const onBlur = () => setArmed(false)
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', onBlur)
    }
  }, [])

  const onArmMouseDown = useCallback(
    (event: ReactMouseEvent) => {
      if (!event.altKey || !wrapRef.current) return
      event.preventDefault()
      // Snapshot the wrap's box once; the drag stays in this coordinate frame
      // even if the layout shifts, and node hit-testing uses the same origin.
      const bounds = wrapRef.current.getBoundingClientRect()
      const startX = event.clientX - bounds.left
      const startY = event.clientY - bounds.top
      setRect({ left: startX, top: startY, width: 0, height: 0 })

      const onMove = (moveEvent: globalThis.MouseEvent) => {
        const currentX = moveEvent.clientX - bounds.left
        const currentY = moveEvent.clientY - bounds.top
        setRect({
          left: Math.min(startX, currentX),
          top: Math.min(startY, currentY),
          width: Math.abs(currentX - startX),
          height: Math.abs(currentY - startY),
        })
      }

      const onUp = (upEvent: globalThis.MouseEvent) => {
        window.removeEventListener('mousemove', onMove)
        window.removeEventListener('mouseup', onUp)
        setRect(null)
        const endX = upEvent.clientX - bounds.left
        const endY = upEvent.clientY - bounds.top
        const xMin = Math.min(startX, endX)
        const xMax = Math.max(startX, endX)
        const yMin = Math.min(startY, endY)
        const yMax = Math.max(startY, endY)
        // A negligible drag is really an alt-click on empty space → deselect.
        if (xMax - xMin < CLICK_SLOP && yMax - yMin < CLICK_SLOP) {
          dispatch(nodeSelectionCleared())
          return
        }
        const forceGraph = fgRef.current
        if (!forceGraph?.graph2ScreenCoords) return
        const caught: string[] = []
        for (const node of viewRef.current.nodes) {
          if (typeof node.x !== 'number' || typeof node.y !== 'number') continue
          const screen = forceGraph.graph2ScreenCoords(node.x, node.y)
          if (screen.x >= xMin && screen.x <= xMax && screen.y >= yMin && screen.y <= yMax) {
            caught.push(node.id)
          }
        }
        // Additive: union this rectangle onto the current pick so several
        // sweeps build one scope. Reset is alt-click / Clear, not a fresh drag.
        dispatch(nodeSelectionAdded(caught))
      }

      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
    },
    [dispatch, fgRef, wrapRef],
  )

  return { armed, rect, onArmMouseDown }
}
