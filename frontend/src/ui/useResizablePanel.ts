/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Drag-to-resize for a docked side panel, with the chosen width
 * remembered across sessions (localStorage).
 *
 * The detail panel and the assistant panel dock on the right (border on their
 * left edge), so their handle lives on that inner-left edge: dragging it
 * *left* widens the panel. The left rail is the mirror image — hence `side`,
 * which flips the sign of the drag and nothing else. The hook owns only the
 * width number + the pointer bookkeeping; the caller renders the panel with
 * `style={{ width }}` and drops a handle element wired to
 * `onHandlePointerDown`.
 *
 * **The clamp is viewport-aware, and the chosen width survives it.** A width
 * in px alone is a promise the window cannot always keep: a panel dragged to
 * 600px on a big monitor stayed 600px in a small window, and since the panels
 * are `flex-shrink: 0` it was the canvas — not the panel — that gave, until
 * the layout overflowed and the page scrolled sideways. So the max is also
 * capped at `maxFraction` of the window (re-read on resize), and no panel may
 * take more than that share of the screen. What the reader *chose* is stored
 * unclamped and only the rendered width is capped, so widening the window
 * hands the width straight back.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

interface ResizeBounds {
  /** Narrowest the panel may get, px. Yields to `maxFraction` in a window too
   *  small to honour it — a floor wider than the ceiling is not a floor. */
  min?: number
  /** Widest the panel may get, px. */
  max?: number
  /** Share of the window the panel may occupy at most (0–1). The px `max`
   *  and this both apply; the smaller wins. */
  maxFraction?: number
  /** Which edge the panel is docked against. A right-docked panel widens as
   *  the pointer moves left; a left-docked one as it moves right. */
  side?: 'left' | 'right'
}

/**
 * The widest the panel may be right now: the px ceiling, capped by the
 * window's current width.
 *
 * @param max         The px ceiling.
 * @param maxFraction Share of the window the panel may occupy.
 * @returns The effective ceiling in px (just `max` with no window — the hook
 *          is exercised in node-environment tests too).
 */
function viewportCeiling(max: number, maxFraction: number): number {
  if (typeof window === 'undefined') return max
  return Math.min(max, Math.round(window.innerWidth * maxFraction))
}

export interface ResizablePanel {
  /** Current width in px — apply as the panel root's inline `width`. */
  width: number
  /** Wire to the drag handle's `onPointerDown`. */
  onHandlePointerDown: (event: ReactPointerEvent) => void
  /** True mid-drag — add a class so the handle can show an active state. */
  dragging: boolean
}

/**
 * @param storageKey    localStorage key the chosen width persists under.
 * @param defaultWidth  Width before the user has ever dragged (must match the
 *                      panel's CSS width so nothing shifts on first paint).
 * @param bounds        Optional min/max/fraction clamp (defaults 280–680px,
 *                      and never more than 40% of the window).
 * @returns The width + drag-handle wiring (see {@link ResizablePanel}).
 */
export function useResizablePanel(
  storageKey: string,
  defaultWidth: number,
  { min = 280, max = 680, maxFraction = 0.4, side = 'right' }: ResizeBounds = {},
): ResizablePanel {
  // The window's contribution to the ceiling, kept in state so a resize
  // re-renders the panel at its new cap.
  const [ceiling, setCeiling] = useState(() => viewportCeiling(max, maxFraction))
  useEffect(() => {
    const onResize = () => setCeiling(viewportCeiling(max, maxFraction))
    // Also once on mount: the window may have been resized between the state
    // initialiser above and this effect (and, in tests, before either).
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [max, maxFraction])

  // In a window too narrow for even `min`, the floor gives way rather than the
  // canvas: a panel wider than its share of the screen is the bug being fixed.
  const clamp = useCallback(
    (value: number) => Math.min(ceiling, Math.max(Math.min(min, ceiling), value)),
    [min, ceiling],
  )

  // What the READER chose, stored and restored unclamped. The rendered width
  // is this capped to the window, so narrowing the window borrows the width
  // and widening it gives the choice back.
  const [chosen, setChosen] = useState<number>(() => {
    const stored = Number(localStorage.getItem(storageKey))
    return Number.isFinite(stored) && stored > 0 ? stored : defaultWidth
  })
  const width = clamp(chosen)
  const [dragging, setDragging] = useState(false)
  // Drag origin, captured on pointer-down; null when not dragging.
  const origin = useRef<{ startX: number; startWidth: number } | null>(null)
  // Mirror of the latest width so the pointer-up persist reads the final value
  // without re-subscribing the window listeners on every move.
  const widthRef = useRef(width)
  widthRef.current = width

  const onHandlePointerDown = useCallback((event: ReactPointerEvent) => {
    event.preventDefault()
    origin.current = { startX: event.clientX, startWidth: widthRef.current }
    setDragging(true)
  }, [])

  useEffect(() => {
    if (!dragging) return
    const onMove = (event: PointerEvent) => {
      const start = origin.current
      if (!start) return
      // Right-docked: leftward drag (smaller clientX) widens. Left-docked is
      // the mirror — the pointer moves away from the panel's own edge either
      // way, which is the only thing that has to feel the same.
      const travelled =
        side === 'left' ? event.clientX - start.startX : start.startX - event.clientX
      // Clamped as it moves, so the handle never runs away from the edge it is
      // dragging — the reader's "choice" is what the drag could actually reach.
      setChosen(clamp(start.startWidth + travelled))
    }
    const onUp = () => {
      origin.current = null
      setDragging(false)
      localStorage.setItem(storageKey, String(Math.round(widthRef.current)))
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [dragging, clamp, storageKey, side])

  return { width, onHandlePointerDown, dragging }
}
