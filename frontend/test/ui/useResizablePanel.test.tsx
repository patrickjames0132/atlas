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
