// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The drag-to-resize hook: width seeding (default vs. stored), the
 * right-docked drag direction (leftward = wider), bound clamping, and the
 * pointer-up persist — plus the viewport cap (v7.10.0), which is what keeps a
 * panel dragged wide on a big monitor from pushing the canvas off a small
 * window. The reader's chosen width outlives the cap: it is stored unclamped,
 * so widening the window hands it straight back.
 *
 * Plus fold-by-drag (v7.11.0), which has three cases worth pinning: bottoming
 * out at `min` must *not* fold the panel away, a deliberate overshoot must —
 * restoring the width they had, since the panel will be reopened — and the
 * folded panel's own handle must pull it back open, measuring from the width
 * it shows rather than the width it remembers.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { useResizablePanel } from '../../src/ui/useResizablePanel'

const STORAGE_KEY = 'test.panelWidth'

/** Resize the (jsdom) window, the way the hook's listener hears about it. */
function setViewport(innerWidth: number) {
  window.innerWidth = innerWidth
  window.dispatchEvent(new Event('resize'))
}

beforeEach(() => {
  // Wide enough that the px bounds, not the viewport, decide — each test that
  // cares about the cap narrows the window itself.
  window.innerWidth = 2000
})

afterEach(() => {
  localStorage.clear()
})

/** The minimal shape onHandlePointerDown reads off the React pointer event. */
function pointerDownAt(clientX: number): ReactPointerEvent {
  return { preventDefault: () => {}, clientX } as unknown as ReactPointerEvent
}

/** Fire a window-level pointer move/up the hook's drag listeners receive. */
function firePointer(type: 'pointermove' | 'pointerup', clientX = 0) {
  window.dispatchEvent(new MouseEvent(type, { clientX }))
}

describe('useResizablePanel', () => {
  it('starts at the default width when nothing is stored', () => {
    const { result } = renderHook(() => useResizablePanel(STORAGE_KEY, 340))
    expect(result.current.width).toBe(340)
    expect(result.current.dragging).toBe(false)
  })

  it('restores a stored width, clamped to the bounds', () => {
    localStorage.setItem(STORAGE_KEY, '500')
    expect(renderHook(() => useResizablePanel(STORAGE_KEY, 340)).result.current.width).toBe(500)

    localStorage.setItem(STORAGE_KEY, '9999')
    expect(renderHook(() => useResizablePanel(STORAGE_KEY, 340)).result.current.width).toBe(680)
  })

  it('ignores garbage in storage and uses the default', () => {
    localStorage.setItem(STORAGE_KEY, 'not-a-number')
    expect(renderHook(() => useResizablePanel(STORAGE_KEY, 340)).result.current.width).toBe(340)
  })

  it('widens on leftward drag (right-docked panel) and persists on release', () => {
    const { result } = renderHook(() => useResizablePanel(STORAGE_KEY, 340))

    act(() => result.current.onHandlePointerDown(pointerDownAt(1000)))
    expect(result.current.dragging).toBe(true)

    act(() => firePointer('pointermove', 900)) // 100px left → 100px wider
    expect(result.current.width).toBe(440)

    act(() => firePointer('pointerup'))
    expect(result.current.dragging).toBe(false)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('440')
  })

  it('clamps mid-drag to the min/max bounds', () => {
    const { result } = renderHook(() => useResizablePanel(STORAGE_KEY, 340, { min: 300, max: 400 }))

    act(() => result.current.onHandlePointerDown(pointerDownAt(1000)))
    act(() => firePointer('pointermove', 0)) // absurdly far left
    expect(result.current.width).toBe(400)

    act(() => firePointer('pointermove', 2000)) // absurdly far right
    expect(result.current.width).toBe(300)
    act(() => firePointer('pointerup'))
  })

  it('caps the width at its share of the window, and gives it back on widening', () => {
    localStorage.setItem(STORAGE_KEY, '600')
    const { result } = renderHook(() => useResizablePanel(STORAGE_KEY, 340))
    expect(result.current.width).toBe(600)

    // 40% of a 1000px window is 400 — the reader's 600 no longer fits.
    act(() => setViewport(1000))
    expect(result.current.width).toBe(400)

    // Their choice was never overwritten, only capped.
    act(() => setViewport(2000))
    expect(result.current.width).toBe(600)
  })

  it('lets the min give way in a window too narrow to honour it', () => {
    // 40% of 600px is 240 — narrower than the 280px floor, which must yield:
    // a panel wider than its share of the screen is the bug being fixed.
    window.innerWidth = 600
    const { result } = renderHook(() => useResizablePanel(STORAGE_KEY, 340))
    expect(result.current.width).toBe(240)
  })

  it('collapses when a drag is hauled well past the floor', () => {
    let toggles = 0
    const { result } = renderHook(() =>
      useResizablePanel(STORAGE_KEY, 240, {
        min: 180,
        max: 380,
        side: 'left',
        fold: {
          collapsed: false,
          collapsedWidth: 56,
          closeAt: 130,
          openAt: 96,
          onToggle: () => {
            toggles += 1
          },
        },
      }),
    )

    act(() => result.current.onHandlePointerDown(pointerDownAt(240)))
    // Left-docked: rightward widens, so 60px LEFT is 180 — the floor, not the
    // collapse. Bottoming out must not fold the panel away.
    act(() => firePointer('pointermove', 180))
    expect(toggles).toBe(0)
    expect(result.current.width).toBe(180)

    act(() => firePointer('pointermove', 140)) // → 140: past the floor, above 130
    expect(toggles).toBe(0)

    act(() => firePointer('pointermove', 100)) // → 100, well under 130
    expect(toggles).toBe(1)
    // The drag is over, and the width they had is what comes back on reopen —
    // a floor-width sliver would make re-expanding feel like a reset.
    expect(result.current.dragging).toBe(false)
    expect(result.current.width).toBe(240)

    act(() => firePointer('pointerup'))
    expect(toggles).toBe(1)
  })

  it('pulls the folded panel back open, measuring from the width it shows', () => {
    localStorage.setItem(STORAGE_KEY, '300')
    let toggles = 0
    const { result } = renderHook(() =>
      useResizablePanel(STORAGE_KEY, 240, {
        min: 180,
        max: 380,
        side: 'left',
        fold: {
          collapsed: true,
          collapsedWidth: 56,
          closeAt: 130,
          openAt: 96,
          onToggle: () => {
            toggles += 1
          },
        },
      }),
    )

    act(() => result.current.onHandlePointerDown(pointerDownAt(56)))
    // 300px is remembered, 56px is on screen: measured from the remembered
    // width, this 20px pull would already have crossed `openAt` at rest.
    act(() => firePointer('pointermove', 76))
    expect(toggles).toBe(0)

    act(() => firePointer('pointermove', 120)) // 64px of pull → 120, past 96
    expect(toggles).toBe(1)
    expect(result.current.dragging).toBe(false)
    // Nothing was sized on the way out: the rail comes back at its own width.
    expect(result.current.width).toBe(300)
    act(() => firePointer('pointerup'))
  })

  it('stops at the floor when no collapse is wired up', () => {
    const { result } = renderHook(() =>
      useResizablePanel(STORAGE_KEY, 240, { min: 180, max: 380, side: 'left' }),
    )
    act(() => result.current.onHandlePointerDown(pointerDownAt(240)))
    act(() => firePointer('pointermove', 0))
    expect(result.current.width).toBe(180)
    expect(result.current.dragging).toBe(true)
    act(() => firePointer('pointerup'))
  })

  it('will not let a drag exceed the viewport cap', () => {
    window.innerWidth = 1000
    const { result } = renderHook(() => useResizablePanel(STORAGE_KEY, 340))

    act(() => result.current.onHandlePointerDown(pointerDownAt(1000)))
    act(() => firePointer('pointermove', 0)) // drag hard left
    expect(result.current.width).toBe(400)
    act(() => firePointer('pointerup'))
    expect(localStorage.getItem(STORAGE_KEY)).toBe('400')
  })
})
