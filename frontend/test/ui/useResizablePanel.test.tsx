// @vitest-environment jsdom
/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The drag-to-resize hook: width seeding (default vs. stored), the
 * right-docked drag direction (leftward = wider), bound clamping, and the
 * pointer-up persist.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import { afterEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { useResizablePanel } from '../../src/ui/useResizablePanel'

const STORAGE_KEY = 'test.panelWidth'

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
})
