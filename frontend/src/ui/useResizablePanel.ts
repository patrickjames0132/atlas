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
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

interface ResizeBounds {
  /** Narrowest the panel may get, px. */
  min?: number
  /** Widest the panel may get, px. */
  max?: number
  /** Which edge the panel is docked against. A right-docked panel widens as
   *  the pointer moves left; a left-docked one as it moves right. */
  side?: 'left' | 'right'
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
 * @param bounds        Optional min/max clamp (defaults 280–680px).
 * @returns The width + drag-handle wiring (see {@link ResizablePanel}).
 */
export function useResizablePanel(
  storageKey: string,
  defaultWidth: number,
  { min = 280, max = 680, side = 'right' }: ResizeBounds = {},
): ResizablePanel {
  const clamp = useCallback((value: number) => Math.min(max, Math.max(min, value)), [min, max])

  const [width, setWidth] = useState<number>(() => {
    const stored = Number(localStorage.getItem(storageKey))
    return Number.isFinite(stored) && stored > 0 ? clamp(stored) : defaultWidth
  })
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
      setWidth(clamp(start.startWidth + travelled))
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
